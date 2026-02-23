"""
Full-pipeline GitHub repository scanner.

Usage:
    python scan_github_repo.py <owner> <repo> [--no-issues] [--no-rag]

Example:
    python scan_github_repo.py jay-nagulavancha spring-boot-spring-security-jwt-authentication
"""
import os
import sys
import json
import argparse
from datetime import datetime

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

from app.services.scan_service import ScanService
from app.services.llm_service import LLMService
from app.services.rag_service import RAGService
from app.services.mcp_github_service import MCPGitHubService


def print_header(owner: str, repo: str):
    print()
    print("=" * 70)
    print(f"  Code Intelligence Platform — Full Scan Pipeline")
    print(f"  Repository: {owner}/{repo}")
    print(f"  Time:       {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)


def on_progress(step: int, message: str):
    print(f"\n{'─' * 50}")
    print(f"  Step {step}: {message}")
    print(f"{'─' * 50}")


def print_service_status(llm: LLMService, rag, github: MCPGitHubService):
    print(f"\n  Service status:")
    if llm.is_available():
        cfg = llm.get_config()
        llm_status = f"✅ {llm.provider}/{llm.model} (ctx={cfg.get('num_ctx','?')}, max_tok={cfg['max_tokens']}, timeout={cfg['timeout']}s)"
    else:
        llm_status = "⚠️  unavailable (reports will use fallback)"
    print(f"    LLM     : {llm_status}")
    if rag is None:
        print(f"    RAG     : ⏭️  skipped (--no-rag)")
    else:
        try:
            avail = rag.is_available()
            print(f"    RAG     : {'✅ ' + rag.vector_db_type if avail else '⚠️  unavailable'}")
        except Exception:
            print(f"    RAG     : ⚠️  failed to initialize")
    gh_status = "✅ connected" if github.is_available() else "❌ no token"
    print(f"    GitHub  : {gh_status}")


def print_scan_results(result: dict):
    """Pretty-print the scan results to the console."""
    report = result.get("report", {})
    raw_results = result.get("raw_results", {})
    agents = result.get("agents_executed", [])

    # --- Agents executed ---
    print(f"\n  Agents executed: {', '.join(agents)}")

    # --- Issue counts by severity ---
    all_issues = report.get("raw_issues", report.get("issues", []))
    by_severity = {}
    for issue in all_issues:
        sev = (issue.get("severity") or "unknown").lower()
        by_severity.setdefault(sev, []).append(issue)

    print(f"\n  {'─' * 40}")
    print(f"  FINDINGS SUMMARY  (total: {len(all_issues)})")
    print(f"  {'─' * 40}")

    for sev in ["critical", "high", "medium", "low", "warning", "info"]:
        count = len(by_severity.get(sev, []))
        if count > 0:
            icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵", "warning": "⚠️", "info": "ℹ️"}.get(sev, "•")
            print(f"    {icon}  {sev.upper():10s}: {count}")

    # --- Detailed issues (top 15 across all severities) ---
    print(f"\n  {'─' * 40}")
    print(f"  DETAILED ISSUES")
    print(f"  {'─' * 40}")
    shown = 0
    for sev in ["critical", "high", "medium", "low"]:
        issues = by_severity.get(sev, [])
        if not issues:
            continue
        print(f"\n  [{sev.upper()}]")
        for i, issue in enumerate(issues[:10], 1):
            msg = issue.get("message", "Unknown")
            file_path = issue.get("file") or ""
            line = issue.get("line") or ""
            tool = issue.get("tool", "")
            loc = f"  {file_path}:{line}" if file_path else ""
            print(f"    {i}. {msg}")
            if loc:
                print(f"       Location:{loc}")
            if tool:
                print(f"       Tool: {tool}")
            shown += 1
        if len(issues) > 10:
            print(f"    ... and {len(issues) - 10} more")

    if shown == 0:
        print("    ✅ No significant issues found!")

    # --- LLM-enhanced content ---
    print(f"\n  {'─' * 40}")
    print(f"  LLM-ENHANCED REPORT")
    print(f"  {'─' * 40}")

    llm_enhanced = result.get("llm_enhanced", False)
    if not llm_enhanced:
        print("    ⚠️  LLM not available — showing raw results only.")
        print("    To enable: start Ollama ('ollama serve') and pull a model.")
    else:
        # Vulnerability suggestions
        suggestions = report.get("vulnerability_suggestions", [])
        if suggestions:
            print(f"\n  🔧 Vulnerability Fix Suggestions ({len(suggestions)}):")
            for i, sug in enumerate(suggestions[:5], 1):
                explanation = sug.get("explanation", sug.get("issue", str(sug)))
                fix = sug.get("fix", sug.get("code_fix", sug.get("suggestion", "")))
                priority = sug.get("priority", "")
                print(f"\n    {i}. [{priority.upper()}] {explanation}")
                if fix:
                    for fix_line in str(fix).splitlines()[:5]:
                        print(f"       {fix_line}")

        # LLM recommendations from combine_outputs
        recommendations = report.get("recommendations", [])
        if recommendations:
            print(f"\n  📋 Recommendations ({len(recommendations)}):")
            for i, rec in enumerate(recommendations[:5], 1):
                if isinstance(rec, dict):
                    print(f"    {i}. {rec.get('title', rec.get('recommendation', str(rec)))}")
                else:
                    print(f"    {i}. {rec}")

        # Next steps
        next_steps = report.get("next_steps", [])
        if next_steps:
            print(f"\n  🚀 Next Steps:")
            for i, step in enumerate(next_steps[:5], 1):
                if isinstance(step, dict):
                    print(f"    {i}. {step.get('title', step.get('step', str(step)))}")
                else:
                    print(f"    {i}. {step}")

        # Deprecation summary
        dep_summary = report.get("deprecation_summary")
        if dep_summary:
            print(f"\n  📦 Deprecation Summary:")
            if isinstance(dep_summary, dict):
                print(f"    {dep_summary.get('summary', json.dumps(dep_summary, indent=4))}")

        # Release notes
        release_notes = report.get("release_notes")
        if release_notes:
            print(f"\n  📝 Release Notes:")
            for rl in str(release_notes).splitlines()[:20]:
                print(f"    {rl}")

    # --- RAG context ---
    hist = result.get("historical_context", {})
    similar = hist.get("similar_scans", [])
    if similar:
        print(f"\n  {'─' * 40}")
        print(f"  HISTORICAL CONTEXT (RAG)")
        print(f"  {'─' * 40}")
        print(f"    Found {len(similar)} similar past scan(s)")
        for scan in similar[:3]:
            print(f"    - Scan {scan.get('scan_id', '?')[:8]}... "
                  f"({len(scan.get('issues', []))} issues, "
                  f"similarity: {scan.get('similarity', 0):.2f})")

    # --- GitHub issues created ---
    gh_issues = result.get("github_issues_created", [])
    if gh_issues:
        print(f"\n  {'─' * 40}")
        print(f"  GITHUB ISSUES CREATED")
        print(f"  {'─' * 40}")
        for gi in gh_issues:
            print(f"    ✅ #{gi.get('number')}: {gi.get('title', '')}")
            print(f"       {gi.get('url', '')}")


def save_results(owner: str, repo: str, result: dict):
    """Save the full result to JSON."""
    filename = f"scan_report_{owner}_{repo}.json"

    # Make the result JSON-serializable (drop non-serializable repo_info fields)
    serializable = {}
    for k, v in result.items():
        try:
            json.dumps(v)
            serializable[k] = v
        except (TypeError, ValueError):
            serializable[k] = str(v)

    with open(filename, 'w') as f:
        json.dump(serializable, f, indent=2, default=str)

    print(f"\n  Full report saved to: {filename}")
    return filename


def main():
    parser = argparse.ArgumentParser(
        description="Code Intelligence Platform — Full Scan Pipeline"
    )
    parser.add_argument("owner", help="GitHub repository owner")
    parser.add_argument("repo", help="GitHub repository name")
    parser.add_argument(
        "--no-issues", action="store_true",
        help="Skip creating GitHub issues for findings"
    )
    parser.add_argument(
        "--no-rag", action="store_true",
        help="Skip storing results in RAG"
    )
    parser.add_argument(
        "--no-llm", action="store_true",
        help="Skip LLM enhancement (faster, no AI-generated suggestions)"
    )
    parser.add_argument(
        "--scan-types", nargs="+", default=["security", "oss"],
        help="Scan types to run (default: security oss)"
    )
    args = parser.parse_args()

    print_header(args.owner, args.repo)

    # Initialize services (lazy — avoid heavy imports until needed)
    llm_service = LLMService()
    github_service = MCPGitHubService()

    # Only initialize RAG if needed (avoids slow torch/sentence-transformers import)
    if args.no_rag:
        rag_service = None
    else:
        try:
            rag_service = RAGService()
        except Exception:
            rag_service = None

    print_service_status(llm_service, rag_service, github_service)

    if not github_service.is_available():
        print("\n  ❌ GITHUB_TOKEN not set. Cannot proceed.")
        sys.exit(1)

    scan_service = ScanService(
        llm_service=llm_service,
        rag_service=rag_service,
        github_service=github_service,
    )

    use_llm = not args.no_llm and llm_service.is_available()

    # Pre-load the model into RAM so the first LLM call doesn't time out
    if use_llm:
        llm_service.warmup()

    try:
        result = scan_service.scan_github_repo(
            owner=args.owner,
            repo=args.repo,
            scan_types=args.scan_types,
            create_issues=not args.no_issues,
            store_in_rag=not args.no_rag,
            use_llm=use_llm,
            on_progress=on_progress,
        )

        print_scan_results(result)
        save_results(args.owner, args.repo, result)

    except Exception as e:
        print(f"\n  ❌ Scan failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print(f"\n{'=' * 70}")
    print(f"  Scan Complete!")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    main()
