"""Anonymous liveness probe (no auth by design — see platform-foundation spec)."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    """Return liveness payload."""
    return {"status": "ok"}
