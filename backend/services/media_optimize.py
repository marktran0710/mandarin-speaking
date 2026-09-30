"""On-demand WebP variants of large uploaded raster images.

Lesson comic panels are ~2.4MB PNGs; the same picture is ~0.2MB as WebP with no
visible difference at classroom sizes. Stored URLs stay untouched: the media
route serves a cached WebP sibling to browsers that accept it and the original
file to everyone else. Variants live next to (not inside) the upload root, so
they are never addressable as uploads themselves.
"""
import logging
import os
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MIN_SOURCE_BYTES = 150 * 1024  # small graphics are not worth the round trip
WEBP_QUALITY = 85
_RASTER_SUFFIXES = {".png", ".jpg", ".jpeg"}
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def is_raster_image(path: Path) -> bool:
    return path.suffix.lower() in _RASTER_SUFFIXES


def accepts_webp(accept_header: Optional[str]) -> bool:
    return bool(accept_header) and "image/webp" in accept_header.lower()


def cache_root_for(upload_root: Path) -> Path:
    return upload_root.with_name(f"{upload_root.name}-cache")


def _lock_for(key: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


def _is_fresh(variant: Path, source: Path) -> bool:
    return variant.is_file() and variant.stat().st_mtime >= source.stat().st_mtime


def webp_variant(source: Path, upload_root: Path) -> Optional[Path]:
    """Path of a cached WebP for ``source``, creating it on first use.

    ``None`` means "serve the original": not a large raster image, Pillow is
    unavailable, encoding failed, or WebP would not be smaller.
    """
    if not is_raster_image(source) or source.stat().st_size < MIN_SOURCE_BYTES:
        return None
    variant = cache_root_for(upload_root) / f"{source.relative_to(upload_root).as_posix()}.webp"
    skip_marker = variant.with_name(f"{variant.name}.skip")
    if _is_fresh(variant, source):
        return variant
    if _is_fresh(skip_marker, source):
        return None
    with _lock_for(str(variant)):
        if _is_fresh(variant, source):
            return variant
        try:
            from PIL import Image
        except ImportError:
            logger.warning("Pillow is not installed; serving original images without WebP variants.")
            return None
        tmp = variant.with_name(f"{variant.name}.{os.getpid()}.tmp")
        try:
            variant.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(source) as image:
                image.load()
                image.save(tmp, "WEBP", quality=WEBP_QUALITY, method=4)
            if tmp.stat().st_size >= source.stat().st_size:
                tmp.unlink()
                skip_marker.touch()
                return None
            os.replace(tmp, variant)
            return variant
        except Exception:
            logger.warning("Could not build a WebP variant for %s; serving the original.", source, exc_info=True)
            tmp.unlink(missing_ok=True)
            return None
