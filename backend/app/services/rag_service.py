"""
RAG Service - Retrieval Augmented Generation using vector databases
for storing and querying historical scans, issues, and code snippets.
"""
import os
import json
from typing import List, Dict, Any, Optional
from pathlib import Path


class RAGService:
    """
    RAG Service for storing and retrieving historical context.
    Supports FAISS and Qdrant vector databases.
    """

    def __init__(
        self, 
        vector_db_type: str = "faiss",
        persist_dir: Optional[str] = None
    ):
        """
        Initialize RAG service.
        
        Args:
            vector_db_type: Type of vector DB ("faiss" or "qdrant")
            persist_dir: Directory to persist vector DB
        """
        self.vector_db_type = vector_db_type
        self.persist_dir = persist_dir or os.getenv(
            "VECTOR_DB_DIR", 
            os.path.join(os.getcwd(), ".vector_db")
        )
        Path(self.persist_dir).mkdir(parents=True, exist_ok=True)
        
        self._vector_db = None
        self._embeddings = None
        self._initialized = False
        self._metadata = []
        self._client = None
        self._collection_name = None

    def _initialize_faiss(self):
        """Initialize FAISS vector database."""
        try:
            import faiss
            from sentence_transformers import SentenceTransformer
            
            self._embeddings = SentenceTransformer('all-MiniLM-L6-v2')
            
            # Load or create FAISS index
            index_path = os.path.join(self.persist_dir, "faiss.index")
            metadata_path = os.path.join(self.persist_dir, "metadata.json")
            
            if os.path.exists(index_path):
                self._vector_db = faiss.read_index(index_path)
                with open(metadata_path, 'r') as f:
                    self._metadata = json.load(f)
            else:
                # Create new index (384 dimensions for all-MiniLM-L6-v2)
                dimension = 384
                self._vector_db = faiss.IndexFlatL2(dimension)
                self._metadata = []
            
            self._initialized = True
            
        except ImportError as e:
            raise RuntimeError(
                f"FAISS dependencies not installed. Run: pip install faiss-cpu sentence-transformers"
            )

    def _initialize_qdrant(self):
        """Initialize Qdrant vector database."""
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams
            from sentence_transformers import SentenceTransformer
            
            self._embeddings = SentenceTransformer('all-MiniLM-L6-v2')
            
            # Initialize Qdrant client
            qdrant_url = os.getenv("QDRANT_URL", "localhost")
            qdrant_port = int(os.getenv("QDRANT_PORT", "6333"))
            
            self._client = QdrantClient(host=qdrant_url, port=qdrant_port)
            collection_name = "code_intelligence"
            
            # Create collection if it doesn't exist
            try:
                self._client.get_collection(collection_name)
            except Exception:
                self._client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=384,  # all-MiniLM-L6-v2 dimension
                        distance=Distance.COSINE
                    )
                )
            
            self._collection_name = collection_name
            self._initialized = True
            
        except ImportError as e:
            raise RuntimeError(
                f"Qdrant dependencies not installed. Run: pip install qdrant-client sentence-transformers"
            )

    def initialize(self):
        """Initialize the vector database."""
        if self._initialized:
            return

        if self.vector_db_type == "faiss":
            self._initialize_faiss()
        elif self.vector_db_type == "qdrant":
            self._initialize_qdrant()
        else:
            raise ValueError(f"Unsupported vector DB type: {self.vector_db_type}")

    def is_available(self) -> bool:
        """Check if RAG service is available."""
        try:
            if not self._initialized:
                self.initialize()
            return True
        except Exception as e:
            print(f"RAG service not available: {e}")
            return False

    def _get_embedding(self, text: str) -> List[float]:
        """Get embedding for text."""
        if not self._embeddings:
            raise RuntimeError("Embeddings model not initialized")
        return self._embeddings.encode(text).tolist()

    def store_scan(
        self, 
        scan_id: str, 
        issues: List[Dict], 
        project_context: Dict[str, Any],
        code_snippets: Optional[List[str]] = None
    ):
        """
        Store scan results in vector database.
        
        Args:
            scan_id: Unique identifier for the scan
            issues: List of issues found
            code_snippets: Relevant code snippets
        """
        if not self.is_available():
            return

        # Create text representation
        text_parts = [
            f"Scan ID: {scan_id}",
            f"Project: {project_context.get('name', 'unknown')}",
            f"Issues found: {len(issues)}"
        ]

        # Add issue summaries
        for issue in issues[:10]:  # Limit to first 10 issues
            issue_text = f"Issue type: {issue.get('type')}, "
            if 'message' in issue:
                issue_text += f"Message: {issue['message']}"
            elif 'package' in issue:
                issue_text += f"Package: {issue['package']}"
            text_parts.append(issue_text)

        # Add code snippets
        if code_snippets:
            text_parts.extend([f"Code: {snippet[:200]}" for snippet in code_snippets[:5]])

        text = " ".join(text_parts)
        embedding = self._get_embedding(text)

        if self.vector_db_type == "faiss":
            # Store in FAISS
            self._vector_db.add(embedding.reshape(1, -1))
            self._metadata.append({
                "scan_id": scan_id,
                "issues": issues,
                "project_context": project_context,
                "code_snippets": code_snippets
            })
            
            # Persist
            faiss.write_index(self._vector_db, os.path.join(self.persist_dir, "faiss.index"))
            with open(os.path.join(self.persist_dir, "metadata.json"), 'w') as f:
                json.dump(self._metadata, f)

        elif self.vector_db_type == "qdrant":
            # Store in Qdrant
            from qdrant_client.models import PointStruct
            
            self._client.upsert(
                collection_name=self._collection_name,
                points=[
                    PointStruct(
                        id=hash(scan_id) % (2**63),  # Convert to int64
                        vector=embedding,
                        payload={
                            "scan_id": scan_id,
                            "issues": issues,
                            "project_context": project_context,
                            "code_snippets": code_snippets or []
                        }
                    )
                ]
            )

    def query_similar_scans(
        self, 
        query: str, 
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Query for similar historical scans.
        
        Args:
            query: Search query
            top_k: Number of results to return
        
        Returns:
            List of similar scans with metadata
        """
        if not self.is_available():
            return []

        query_embedding = self._get_embedding(query)

        if self.vector_db_type == "faiss":
            # Search in FAISS
            if self._vector_db.ntotal == 0:
                return []

            distances, indices = self._vector_db.search(
                query_embedding.reshape(1, -1), 
                top_k
            )

            results = []
            for idx, dist in zip(indices[0], distances[0]):
                if idx < len(self._metadata):
                    result = self._metadata[idx].copy()
                    result["similarity"] = float(1 / (1 + dist))  # Convert distance to similarity
                    results.append(result)

            return results

        elif self.vector_db_type == "qdrant":
            # Search in Qdrant
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            
            search_results = self._client.search(
                collection_name=self._collection_name,
                query_vector=query_embedding,
                limit=top_k
            )

            results = []
            for result in search_results:
                results.append({
                    **result.payload,
                    "similarity": result.score
                })

            return results

    def get_historical_context(
        self, 
        current_issues: List[Dict],
        project_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Get relevant historical context for current scan.
        
        Args:
            current_issues: Current scan issues
            project_context: Current project context
        
        Returns:
            Historical context with similar scans and patterns
        """
        if not self.is_available():
            return {"similar_scans": [], "patterns": []}

        # Create query from current issues
        query_parts = [
            f"Project: {project_context.get('name', 'unknown')}"
        ]
        
        for issue in current_issues[:5]:
            if 'message' in issue:
                query_parts.append(issue['message'])
            elif 'package' in issue:
                query_parts.append(issue['package'])

        query = " ".join(query_parts)
        similar_scans = self.query_similar_scans(query, top_k=5)

        # Extract patterns from similar scans
        patterns = {}
        for scan in similar_scans:
            for issue in scan.get("issues", []):
                issue_type = issue.get("type", "unknown")
                if issue_type not in patterns:
                    patterns[issue_type] = []
                patterns[issue_type].append(issue)

        return {
            "similar_scans": similar_scans,
            "patterns": patterns,
            "total_historical_scans": len(similar_scans)
        }
