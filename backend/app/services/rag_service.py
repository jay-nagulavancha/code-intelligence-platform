"""
RAG Service - Retrieval Augmented Generation using vector databases
for storing and querying historical scans, issues, and code snippets.
"""
import os
import sys
import json
import logging
import warnings
from typing import List, Dict, Any, Optional
from pathlib import Path

# Quiet down transformers/HF before they are imported elsewhere. These cover
# the most common noise (loading reports, progress bars) emitted via the
# upstream logging module. The hard stdout/stderr redirect in
# _suppress_noisy_loggers below catches anything that bypasses logging
# (for example, transformers' tabulated "UNEXPECTED" key report which is
# printed directly to stdout in newer versions).
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("HF_HUB_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

logger = logging.getLogger(__name__)

# Default embedding model — 384-dim vectors (must match existing FAISS index / Qdrant collection).
_DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class RAGService:
    """
    RAG Service for storing and retrieving historical context.
    Supports FAISS and Qdrant vector databases.
    All import/init errors are handled gracefully — the service
    simply marks itself unavailable without noisy tracebacks.
    """

    def __init__(
        self,
        vector_db_type: Optional[str] = None,
        persist_dir: Optional[str] = None,
    ):
        raw = (vector_db_type or os.getenv("VECTOR_DB_TYPE") or "faiss").strip().lower()
        self.vector_db_type = raw if raw in ("faiss", "qdrant") else "faiss"
        self.persist_dir = persist_dir or os.getenv(
            "VECTOR_DB_DIR",
            os.path.join(os.getcwd(), ".vector_db"),
        )
        Path(self.persist_dir).mkdir(parents=True, exist_ok=True)

        self._vector_db = None
        self._embeddings = None
        self._initialized = False
        self._init_error: Optional[str] = None
        self._metadata: List[Dict] = []
        self._client = None
        self._collection_name: Optional[str] = None

    def _reset_rag_init_state(self) -> None:
        """Clear partial init so we can retry (e.g. Qdrant → FAISS fallback)."""
        self._embeddings = None
        self._vector_db = None
        self._client = None
        self._collection_name = None
        self._metadata = []
        self._initialized = False

    # ------------------------------------------------------------------
    # Initialisation (lazy, quiet)
    # ------------------------------------------------------------------

    @staticmethod
    def _suppress_noisy_loggers():
        """
        Context manager that silences transformers/HF/sentence-transformers
        output during model load:

          - Lowers the upstream logging modules to CRITICAL.
          - Calls `transformers.logging.set_verbosity_error()` if available.
          - Redirects sys.stdout / sys.stderr to /dev/null so things printed
            directly (notably transformers' tabulated loading report with
            entries like `embeddings.position_ids | UNEXPECTED`, which is
            emitted via plain `print()` in newer versions and therefore
            bypasses Python logging entirely) cannot reach the demo console.

        Exceptions raised inside the context are still propagated normally,
        so genuine errors during model load are not hidden.
        """
        import contextlib

        @contextlib.contextmanager
        def _ctx():
            noisy = [
                "transformers",
                "transformers.utils.loading_report",
                "transformers.modeling_utils",
                "sentence_transformers",
                "sentence_transformers.SentenceTransformer",
                "huggingface_hub",
                "huggingface_hub.utils._http",
                "huggingface_hub.file_download",
            ]
            saved_levels = {}
            for name in noisy:
                lg = logging.getLogger(name)
                saved_levels[name] = lg.level
                lg.setLevel(logging.CRITICAL)

            root = logging.getLogger()
            saved_handlers = root.handlers[:]
            root.handlers = []

            saved_hf_verbosity = None
            try:
                from transformers.utils import logging as hf_logging
                saved_hf_verbosity = hf_logging.get_verbosity()
                hf_logging.set_verbosity_error()
                hf_logging.disable_progress_bar()
            except Exception:
                pass

            saved_stdout = sys.stdout
            saved_stderr = sys.stderr
            devnull = open(os.devnull, "w")
            sys.stdout = devnull
            sys.stderr = devnull

            try:
                yield
            finally:
                sys.stdout = saved_stdout
                sys.stderr = saved_stderr
                try:
                    devnull.close()
                except Exception:
                    pass

                if saved_hf_verbosity is not None:
                    try:
                        from transformers.utils import logging as hf_logging
                        hf_logging.set_verbosity(saved_hf_verbosity)
                    except Exception:
                        pass

                root.handlers = saved_handlers
                for name, level in saved_levels.items():
                    logging.getLogger(name).setLevel(level)

        return _ctx()

    def _load_sentence_transformer(self):
        """
        Load embedding model from a local directory, Hugging Face cache, or Hub.

        Vector DB files (FAISS under VECTOR_DB_DIR) are always local; the *model
        weights* are separate. First Hub use downloads into HF cache (~/.cache/huggingface
        or HF_HOME); thereafter use HF_HUB_OFFLINE=1 or RAG_LOCAL_FILES_ONLY=1 to
        avoid any network. Or set RAG_EMBEDDING_MODEL to an absolute path to a
        saved model folder (no download).
        """
        from sentence_transformers import SentenceTransformer

        raw = (os.getenv("RAG_EMBEDDING_MODEL") or _DEFAULT_EMBEDDING_MODEL).strip()
        kwargs: Dict[str, Any] = {}
        cache_folder = (
            os.getenv("SENTENCE_TRANSFORMERS_HOME")
            or os.getenv("TRANSFORMERS_CACHE")
            or None
        )
        if cache_folder:
            kwargs["cache_folder"] = cache_folder

        local_only = (
            os.getenv("RAG_LOCAL_FILES_ONLY", "").lower() in ("1", "true", "yes")
            or os.getenv("HF_HUB_OFFLINE", "").lower() in ("1", "true", "yes")
        )
        if local_only:
            kwargs["local_files_only"] = True

        # Local snapshot directory — loads entirely from disk (no Hub).
        if os.path.isdir(raw):
            kwargs.pop("local_files_only", None)
            model_ref = raw
        else:
            model_ref = raw

        return SentenceTransformer(model_ref, **kwargs)

    def _initialize_faiss(self):
        """Initialize FAISS vector database."""
        with self._suppress_noisy_loggers():
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                import faiss  # noqa: F811
            self._embeddings = self._load_sentence_transformer()

        index_path = os.path.join(self.persist_dir, "faiss.index")
        metadata_path = os.path.join(self.persist_dir, "metadata.json")

        if os.path.exists(index_path):
            self._vector_db = faiss.read_index(index_path)
            with open(metadata_path, "r") as f:
                self._metadata = json.load(f)
        else:
            dimension = 384  # all-MiniLM-L6-v2
            self._vector_db = faiss.IndexFlatL2(dimension)
            self._metadata = []

        self._initialized = True

    def _initialize_qdrant(self):
        """Initialize Qdrant vector database."""
        with self._suppress_noisy_loggers():
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                from qdrant_client import QdrantClient
                from qdrant_client.models import Distance, VectorParams
            self._embeddings = self._load_sentence_transformer()

        timeout = int(os.getenv("QDRANT_TIMEOUT_SEC", "15"))
        prefer_grpc = os.getenv("QDRANT_PREFER_GRPC", "false").lower() in (
            "1",
            "true",
            "yes",
        )

        raw = (os.getenv("QDRANT_URL") or "").strip()
        common_kw = {
            "timeout": timeout,
            "check_compatibility": False,
            "prefer_grpc": prefer_grpc,
        }

        try:
            if raw.startswith("http://") or raw.startswith("https://"):
                self._client = QdrantClient(url=raw.rstrip("/"), **common_kw)
            else:
                host = raw or "localhost"
                port = int(os.getenv("QDRANT_PORT", "6333"))
                self._client = QdrantClient(host=host, port=port, **common_kw)
        except Exception as e:
            hint = (
                "Use QDRANT_URL=http://127.0.0.1:6333 from the host, or "
                "http://qdrant:6333 from another Docker container on the same network. "
                "Is `docker compose up qdrant` (or your Qdrant service) running?"
            )
            raise RuntimeError(f"{e}. {hint}") from e

        collection_name = "code_intelligence"

        try:
            self._client.get_collection(collection_name)
        except Exception:
            self._client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=384,
                    distance=Distance.COSINE,
                ),
            )

        self._collection_name = collection_name
        self._initialized = True

    def initialize(self):
        """Initialize the vector database (called lazily)."""
        if self._initialized:
            return
        if self._init_error is not None:
            return  # already tried and failed — don't retry

        silent = os.environ.get("RAG_SILENT_INIT", "").lower() in ("1", "true", "yes")
        if not silent:
            emb = (os.getenv("RAG_EMBEDDING_MODEL") or _DEFAULT_EMBEDDING_MODEL).strip()
            local_hint = (
                "from disk (local path)"
                if os.path.isdir(emb)
                else (
                    "cache-only (HF_HUB_OFFLINE/RAG_LOCAL_FILES_ONLY)"
                    if os.getenv("HF_HUB_OFFLINE", "").lower() in ("1", "true", "yes")
                    or os.getenv("RAG_LOCAL_FILES_ONLY", "").lower()
                    in ("1", "true", "yes")
                    else "Hub or HF cache — first run downloads ~90MB unless cached"
                )
            )
            print(
                f"  RAG: initializing — embeddings {local_hint}; "
                f"`--no-rag` skips; RAG_SILENT_INIT=1 hides this.\n",
                flush=True,
            )

        try:
            if self.vector_db_type == "faiss":
                self._initialize_faiss()
            elif self.vector_db_type == "qdrant":
                strict = os.getenv("RAG_STRICT_QDRANT", "").lower() in (
                    "1",
                    "true",
                    "yes",
                )
                try:
                    self._initialize_qdrant()
                except Exception as qerr:
                    if strict:
                        raise
                    self._reset_rag_init_state()
                    brief = str(qerr).strip().split("\n")[0]
                    if len(brief) > 160:
                        brief = brief[:157] + "..."
                    if not silent:
                        print(
                            "  RAG: Qdrant not reachable — using local FAISS instead "
                            f"({brief}). Set RAG_STRICT_QDRANT=1 to fail without fallback.\n",
                            flush=True,
                        )
                    logger.warning("RAG: Qdrant unavailable, falling back to FAISS: %s", qerr)
                    self.vector_db_type = "faiss"
                    self._initialize_faiss()
            else:
                self._init_error = f"Unsupported vector DB type: {self.vector_db_type}"
        except ImportError:
            self._init_error = "RAG dependencies not installed (pip install faiss-cpu sentence-transformers)"
        except Exception as e:
            self._init_error = str(e)

    def is_available(self) -> bool:
        """Check if RAG service is available (quiet, no tracebacks)."""
        if not self._initialized and self._init_error is None:
            self.initialize()
        return self._initialized

    def get_status_message(self) -> str:
        """Human-readable status for CLI output."""
        if self._initialized:
            return f"✅ {self.vector_db_type}"
        if self._init_error:
            return f"⚠️  unavailable ({self._init_error})"
        return "⚠️  not initialized"

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    def _get_embedding(self, text: str):
        """Get embedding vector for text."""
        if not self._embeddings:
            raise RuntimeError("Embeddings model not initialized")
        return self._embeddings.encode(text)

    # ------------------------------------------------------------------
    # Store
    # ------------------------------------------------------------------

    def store_scan(
        self,
        scan_id: str,
        issues: List[Dict],
        project_context: Dict[str, Any],
        code_snippets: Optional[List[str]] = None,
    ):
        """Store scan results in vector database."""
        if not self.is_available():
            return

        text_parts = [
            f"Scan ID: {scan_id}",
            f"Project: {project_context.get('name', 'unknown')}",
            f"Issues found: {len(issues)}",
        ]

        for issue in issues[:10]:
            issue_text = f"Issue type: {issue.get('type')}, "
            if "message" in issue:
                issue_text += f"Message: {issue['message']}"
            elif "package" in issue:
                issue_text += f"Package: {issue['package']}"
            text_parts.append(issue_text)

        if code_snippets:
            text_parts.extend([f"Code: {s[:200]}" for s in code_snippets[:5]])

        text = " ".join(text_parts)
        embedding = self._get_embedding(text)

        if self.vector_db_type == "faiss":
            import faiss as _faiss  # noqa: F811
            import numpy as np

            self._vector_db.add(np.array(embedding).reshape(1, -1))
            self._metadata.append({
                "scan_id": scan_id,
                "issues": issues,
                "project_context": project_context,
                "code_snippets": code_snippets,
            })

            _faiss.write_index(
                self._vector_db,
                os.path.join(self.persist_dir, "faiss.index"),
            )
            with open(os.path.join(self.persist_dir, "metadata.json"), "w") as f:
                json.dump(self._metadata, f)

        elif self.vector_db_type == "qdrant":
            from qdrant_client.models import PointStruct

            self._client.upsert(
                collection_name=self._collection_name,
                points=[
                    PointStruct(
                        id=hash(scan_id) % (2**63),
                        vector=embedding.tolist(),
                        payload={
                            "scan_id": scan_id,
                            "issues": issues,
                            "project_context": project_context,
                            "code_snippets": code_snippets or [],
                        },
                    )
                ],
            )

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query_similar_scans(
        self,
        query: str,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Query for similar historical scans."""
        if not self.is_available():
            return []

        import numpy as np

        query_embedding = self._get_embedding(query)

        if self.vector_db_type == "faiss":
            if self._vector_db.ntotal == 0:
                return []

            distances, indices = self._vector_db.search(
                np.array(query_embedding).reshape(1, -1),
                top_k,
            )

            results = []
            for idx, dist in zip(indices[0], distances[0]):
                if 0 <= idx < len(self._metadata):
                    result = self._metadata[idx].copy()
                    result["similarity"] = float(1 / (1 + dist))
                    results.append(result)
            return results

        elif self.vector_db_type == "qdrant":
            search_results = self._client.search(
                collection_name=self._collection_name,
                query_vector=query_embedding.tolist(),
                limit=top_k,
            )
            return [
                {**r.payload, "similarity": r.score}
                for r in search_results
            ]

        return []

    def get_historical_context(
        self,
        current_issues: List[Dict],
        project_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Get relevant historical context for current scan."""
        if not self.is_available():
            return {"similar_scans": [], "patterns": []}

        query_parts = [f"Project: {project_context.get('name', 'unknown')}"]
        for issue in current_issues[:5]:
            if "message" in issue:
                query_parts.append(issue["message"])
            elif "package" in issue:
                query_parts.append(issue["package"])

        query = " ".join(query_parts)
        similar_scans = self.query_similar_scans(query, top_k=5)

        patterns: Dict[str, list] = {}
        for scan in similar_scans:
            for issue in scan.get("issues", []):
                issue_type = issue.get("type", "unknown")
                patterns.setdefault(issue_type, []).append(issue)

        return {
            "similar_scans": similar_scans,
            "patterns": patterns,
            "total_historical_scans": len(similar_scans),
        }
