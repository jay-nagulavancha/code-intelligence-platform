"""
Entry point for FastAPI application.
"""
from fastapi import FastAPI
from app.api.routes import scans, github

app = FastAPI(
    title='Code Intelligence Platform',
    description='Multi-Agent Code Intelligence Platform with LLM Orchestration and MCP GitHub Integration',
    version='1.0.0'
)

# Include routers
app.include_router(scans.router, prefix="/api", tags=["scans"])
app.include_router(github.router, prefix="/api", tags=["github"])


@app.get('/')
def health():
    """Health check endpoint."""
    return {
        'status': 'ok',
        'service': 'Code Intelligence Platform',
        'version': '1.0.0'
    }


@app.get('/health')
def detailed_health():
    """Detailed health check with service status."""
    from app.services.llm_service import LLMService
    from app.services.rag_service import RAGService
    from app.services.mcp_github_service import MCPGitHubService
    from app.services.langsmith_service import LangSmithTracer
    
    llm_service = LLMService()
    rag_service = RAGService()
    github_service = MCPGitHubService()
    langsmith = LangSmithTracer()
    
    return {
        'status': 'ok',
        'llm_available': llm_service.is_available(),
        'llm_provider': llm_service.provider,
        'llm_model': llm_service.model,
        'rag_available': rag_service.is_available(),
        'vector_db_type': rag_service.vector_db_type,
        'github_available': github_service.is_available(),
        'langsmith_enabled': langsmith.is_enabled(),
        'langsmith_project': langsmith.get_status().get("project")
    }
