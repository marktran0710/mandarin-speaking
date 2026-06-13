"""FastAPI application entry point."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import (
    FRONTEND_DIST,
    UPLOAD_DIR,
    VIBEVOICE_WARM_ON_START,
    get_cors_origins,
    logger,
)
from database import connect_db, init_db
from routers import audio, help, stories, tones
from services.asr import _ensure_vibevoice_load_started


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if VIBEVOICE_WARM_ON_START:
        _ensure_vibevoice_load_started()
    yield


app = FastAPI(title="Speaking App Backend", version="1.0.0", lifespan=lifespan)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(audio.router)
app.include_router(stories.router)
app.include_router(help.router)
app.include_router(tones.router)


@app.get("/health")
async def health_check():
    db_ok = False
    try:
        with connect_db() as db:
            db.execute("SELECT 1").fetchone()
        db_ok = True
    except Exception as exc:
        logger.error("Health check DB failure: %s", exc)
    return {
        "status": "ok" if db_ok else "degraded",
        "service": "Speaking App Backend",
        "database": "ok" if db_ok else "error",
    }


@app.get("/{frontend_path:path}")
async def serve_frontend(frontend_path: str):
    requested = (FRONTEND_DIST / frontend_path).resolve()
    if FRONTEND_DIST.exists() and requested.is_file():
        return FileResponse(requested)
    index = FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    raise HTTPException(
        status_code=404,
        detail="Frontend build not found. Run `npm run build` first.",
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
