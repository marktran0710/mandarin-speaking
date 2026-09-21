from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from config import settings

router = APIRouter()

FRONTEND_DIST = settings.frontend_dist


@router.get("/{frontend_path:path}")
def serve_frontend(frontend_path: str):
    """
    Serve the built React app from the backend port for local single-port use.
    """
    frontend_root = FRONTEND_DIST.resolve()
    requested_file = (FRONTEND_DIST / frontend_path).resolve()

    # Only serve real files that stay inside the build dir. The resolve() +
    # parents check blocks path traversal (e.g. an encoded ../ escaping
    # FRONTEND_DIST); anything else falls through to the SPA index below.
    within_build = requested_file == frontend_root or frontend_root in requested_file.parents
    if within_build and FRONTEND_DIST.exists() and requested_file.is_file():
        # Vite fingerprints asset filenames, so everything under assets/ is
        # immutable and can be cached for a year; other files (index.html,
        # favicon) must revalidate so a new deploy is picked up immediately.
        in_assets = (frontend_root / "assets") in requested_file.parents
        cache = "public, max-age=31536000, immutable" if in_assets else "no-cache"
        return FileResponse(requested_file, headers={"Cache-Control": cache})

    index_file = FRONTEND_DIST / "index.html"
    if index_file.exists():
        return FileResponse(index_file, headers={"Cache-Control": "no-cache"})

    raise HTTPException(
        status_code=404,
        detail="Frontend build not found. Run `npm run build` first.",
    )
