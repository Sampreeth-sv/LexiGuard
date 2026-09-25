from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.config import settings
from app.storage.database import init_db
from app.api import documents, analysis, questions, comparison, checklists, workspace, reports, reminders_api
import logging
import os

logger = logging.getLogger(__name__)

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    os.makedirs(settings.upload_temp_dir, exist_ok=True)
    init_db()
    logger.info("LexiGuard started. GenAI available: %s", settings.genai_available)
    yield
    # Shutdown - cleanup
    logger.info("LexiGuard shutting down.")

app = FastAPI(
    title="LexiGuard API",
    description="Evidence-grounded legal document assistant",
    version="1.0.0",
    lifespan=lifespan
)

# CORS - explicit origins list for security
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers - never expose stack traces
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled error: %s", type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={"error": "An internal error occurred.", "detail": None}
    )

# System status endpoint
@app.get("/api/status")
async def get_system_status():
    return {
        "status": "ok",
        "genai_available": settings.genai_available,
        "gemini_model": settings.gemini_model if settings.genai_available else "none",
        "version": "1.0.0"
    }

# API routes (analysis router first to handle /api/documents/{id}/summary, /signals, /entities)
app.include_router(analysis.router, prefix="/api/documents", tags=["Analysis"])
app.include_router(documents.router, prefix="/api/documents", tags=["Documents"])
app.include_router(workspace.router, tags=["Workspace"])
app.include_router(questions.router, prefix="/api", tags=["Q&A"])
app.include_router(comparison.router, prefix="/api", tags=["Comparison"])
app.include_router(checklists.router, prefix="/api", tags=["Checklists"])
app.include_router(reports.router, tags=["Reports"])
app.include_router(reminders_api.router, tags=["Reminders"])

# Serve frontend static files
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'frontend')
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")
    
    NO_CACHE_HEADERS = {"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"}

    @app.get("/")
    async def serve_frontend():
        return FileResponse(os.path.join(frontend_dir, 'index.html'), headers=NO_CACHE_HEADERS)
    
    @app.get("/{path:path}")
    async def serve_spa(path: str):
        # API requests that reach here are unmatched API routes -> return 404 JSON, NOT index.html
        if path.startswith("api/") or path == "api":
            return JSONResponse(
                status_code=404,
                content={"error": "Not Found", "detail": f"API route '/{path}' not found."}
            )
        file_path = os.path.join(frontend_dir, path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path, headers=NO_CACHE_HEADERS)
        return FileResponse(os.path.join(frontend_dir, 'index.html'), headers=NO_CACHE_HEADERS)

