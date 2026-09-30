"""Large uploaded images are served as cached WebP to browsers that accept it."""
import os
from pathlib import Path

import pytest

import services.media_optimize as media_optimize

pytest.importorskip("PIL")
from PIL import Image  # noqa: E402


def _noisy_png(path: Path, size=(700, 500)) -> None:
    """A PNG comfortably above MIN_SOURCE_BYTES (random-ish pixels compress badly in PNG)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.frombytes("RGB", size, os.urandom(size[0] * size[1] * 3))
    image.save(path, "PNG")
    assert path.stat().st_size > media_optimize.MIN_SOURCE_BYTES


def _photo_like_png(path: Path, size=(1200, 900)) -> None:
    """Smooth gradient plus faint grain: big as PNG, small as WebP - like the
    lesson comic panels."""
    import numpy as np

    path.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7)
    x = np.linspace(0, 255, size[0], dtype=np.float32)[None, :, None]
    y = np.linspace(0, 255, size[1], dtype=np.float32)[:, None, None]
    base = np.concatenate([np.broadcast_to(x, (size[1], size[0], 1)),
                           np.broadcast_to(y, (size[1], size[0], 1)),
                           np.broadcast_to((x + y) / 2, (size[1], size[0], 1))], axis=2)
    grain = rng.integers(-5, 6, size=(size[1], size[0], 3))
    Image.fromarray(np.clip(base + grain, 0, 255).astype("uint8"), "RGB").save(path, "PNG")
    assert path.stat().st_size > media_optimize.MIN_SOURCE_BYTES


@pytest.fixture
def upload_root(tmp_path, monkeypatch):
    import services.media as media_service

    root = tmp_path / "uploads"
    root.mkdir()
    monkeypatch.setattr(media_service, "UPLOAD_DIR", str(root))
    return root


def test_accepts_webp_header_parsing():
    assert media_optimize.accepts_webp("image/avif,image/webp,image/apng,*/*;q=0.8")
    assert not media_optimize.accepts_webp("image/png,*/*")
    assert not media_optimize.accepts_webp(None)


def test_large_png_gets_a_smaller_cached_webp_next_to_the_upload_root(upload_root):
    source = upload_root / "images" / "panel.png"
    _photo_like_png(source)

    variant = media_optimize.webp_variant(source, upload_root)

    assert variant is not None
    assert variant.suffix == ".webp"
    assert media_optimize.cache_root_for(upload_root) in variant.parents
    assert upload_root not in variant.parents  # never addressable as an upload
    assert variant.stat().st_size < source.stat().st_size / 2
    with Image.open(variant) as image:
        assert image.format == "WEBP" and image.size == (1200, 900)


def test_variant_is_reused_until_the_source_changes(upload_root):
    source = upload_root / "images" / "panel.png"
    _photo_like_png(source)
    first = media_optimize.webp_variant(source, upload_root)
    built_at = first.stat().st_mtime_ns

    assert media_optimize.webp_variant(source, upload_root) == first
    assert first.stat().st_mtime_ns == built_at

    _photo_like_png(source, size=(1000, 800))
    os.utime(source, (first.stat().st_mtime + 5, first.stat().st_mtime + 5))
    rebuilt = media_optimize.webp_variant(source, upload_root)
    with Image.open(rebuilt) as image:
        assert image.size == (1000, 800)


def test_small_images_and_non_images_are_left_alone(upload_root):
    small = upload_root / "images" / "icon.png"
    small.parent.mkdir(parents=True)
    Image.new("RGB", (20, 20)).save(small, "PNG")
    audio = upload_root / "audio" / "clip.mp3"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"x" * (media_optimize.MIN_SOURCE_BYTES + 10))

    assert media_optimize.webp_variant(small, upload_root) is None
    assert media_optimize.webp_variant(audio, upload_root) is None


def test_a_webp_that_would_not_be_smaller_is_skipped_once(upload_root):
    source = upload_root / "images" / "noise.png"
    _noisy_png(source)
    # Random pixels compress no better in lossy WebP than in PNG's raw fallback.
    result = media_optimize.webp_variant(source, upload_root)
    if result is None:
        marker = media_optimize.cache_root_for(upload_root) / "images" / "noise.png.webp.skip"
        assert marker.exists()
        assert media_optimize.webp_variant(source, upload_root) is None


def test_media_route_negotiates_webp_and_varies_on_accept(logged_in_student, upload_root, monkeypatch):
    import services.media_access_service as access

    monkeypatch.setattr(access, "is_media_access_allowed", lambda *args, **kwargs: True)
    source = upload_root / "images" / "panel.png"
    _photo_like_png(source)
    client, _ = logged_in_student

    webp = client.get("/uploads/images/panel.png", headers={"Accept": "image/avif,image/webp,*/*"})
    assert webp.status_code == 200
    assert webp.headers["content-type"] == "image/webp"
    assert "Accept" in [token.strip() for token in webp.headers["vary"].split(",")]
    assert len(webp.content) < source.stat().st_size / 2

    original = client.get("/uploads/images/panel.png", headers={"Accept": "image/png,*/*"})
    assert original.headers["content-type"] == "image/png"
    assert original.content == source.read_bytes()
    assert "Accept" in [token.strip() for token in original.headers["vary"].split(",")]


def test_media_route_still_serves_the_original_when_conversion_fails(logged_in_student, upload_root, monkeypatch):
    import services.media_access_service as access

    monkeypatch.setattr(access, "is_media_access_allowed", lambda *args, **kwargs: True)
    monkeypatch.setattr(media_optimize, "webp_variant", lambda *args, **kwargs: None)
    source = upload_root / "images" / "panel.png"
    _photo_like_png(source)
    client, _ = logged_in_student

    response = client.get("/uploads/images/panel.png", headers={"Accept": "image/webp"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == source.read_bytes()
