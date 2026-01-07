"""Health check endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "claudear"}


@router.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "claudear",
        "version": "0.1.0",
        "description": "Autonomous development automation with Claude Code and Linear",
    }
