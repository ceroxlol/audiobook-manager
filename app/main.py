from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
import os
import logging

from .database import get_db, init_db
from .config import config
from .api.endpoints import router as api_router
from .logger import setup_logging
from .middleware.error_handler import ErrorHandlerMiddleware
from .middleware.rate_limiter import RateLimiterMiddleware

# Setup logging first
logger = setup_logging()

# Initialize database
try:
    init_db()
    logger.info("Database initialized successfully")
except Exception as e:
    logger.error(f"Database initialization failed: {e}")

app = FastAPI(
    title=config.get('app.name'),
    version=config.get('app.version'),
    debug=config.get('app.debug'),
    docs_url="/docs" if config.get('app.debug') else None,  # Disable docs in production
    redoc_url="/redoc" if config.get('app.debug') else None  # Disable redoc in production
)

# Add middleware
app.add_middleware(ErrorHandlerMiddleware)
if not config.get('app.debug'):
    app.add_middleware(RateLimiterMiddleware, max_requests=100, window_seconds=60)

# Include API routes
app.include_router(api_router, prefix="/api/v1")

# Serve static files for the web interface
app.mount("/static", StaticFiles(directory="/opt/audiobook-manager/app/static"), name="static")

@app.get("/")
async def read_index():
    return FileResponse("/opt/audiobook-manager/app/static/index.html")

@app.get("/health")
async def health_check():
    try:
        return {
            "status": "healthy", 
            "service": "audiobook-manager",
            "version": config.get('app.version')
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")

@app.on_event("startup")
async def startup_event():
    logger.info("Audiobook Manager starting up...")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Audiobook Manager shutting down...")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=config.get('server.host'),
        port=config.get('server.port'),
        reload=config.get('app.debug'),
        log_config=None
    )