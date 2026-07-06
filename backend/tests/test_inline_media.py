"""Tests for the /api/inline-media endpoint used by story export.

Root cause this guards against: the frontend used to fetch() image/audio URLs
directly from the browser to inline them as base64 for export. Story frames
built via AI image generation (DALL-E / Pollinations.ai) store a raw
third-party URL, and those hosts don't grant CORS permission for arbitrary
origins, so the browser blocked the request ("Failed to fetch" / CORS policy
error). Server-side fetches aren't subject to browser CORS at all, so the
endpoint under test resolves the media on the backend instead.
"""
import os

import pytest


@pytest.fixture()
def uploaded_image(tmp_path, monkeypatch):
    """Points UPLOAD_DIR at a temp dir with one real image file in it."""
    import main

    upload_dir = tmp_path / "uploads"
    (upload_dir / "images").mkdir(parents=True)
    image_bytes = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
        "53de0000000c4944415408d763f8ffff3f0005fe02fea739669d0000000049"
        "454e44ae426082"
    )
    image_path = upload_dir / "images" / "sample.png"
    image_path.write_bytes(image_bytes)

    monkeypatch.setattr(main, "UPLOAD_DIR", str(upload_dir))
    monkeypatch.setattr(main, "IMAGE_UPLOAD_DIR", str(upload_dir / "images"))
    return image_bytes


class TestResolveMediaB64:
    @pytest.mark.asyncio
    async def test_local_upload_path_resolves(self, uploaded_image):
        import main

        result = await main.resolve_media_b64("/uploads/images/sample.png")
        assert result is not None
        data, mime = result
        assert mime == "image/png"
        import base64
        assert base64.b64decode(data) == uploaded_image

    @pytest.mark.asyncio
    async def test_missing_local_file_returns_none(self, uploaded_image):
        import main

        result = await main.resolve_media_b64("/uploads/images/does-not-exist.png")
        assert result is None

    @pytest.mark.asyncio
    async def test_path_traversal_is_rejected(self, uploaded_image):
        import main

        result = await main.resolve_media_b64("/uploads/../../etc/passwd")
        assert result is None

    @pytest.mark.asyncio
    async def test_data_url_passthrough(self):
        import main

        result = await main.resolve_media_b64("data:image/png;base64,QUJD")
        assert result == ("QUJD", "image/png")

    @pytest.mark.asyncio
    async def test_remote_url_fetched_server_side(self, monkeypatch):
        """The whole point of this endpoint: fetch a third-party URL from the
        server (no CORS enforcement applies server-to-server) instead of the
        browser, which is what would otherwise be blocked by CORS."""
        import main
        import httpx

        class FakeResponse:
            status_code = 200
            headers = {"content-type": "audio/mpeg"}
            content = b"fake-remote-bytes"

        class FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def get(self, url):
                assert url == "https://third-party.example/audio.mp3"
                return FakeResponse()

        monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

        result = await main.resolve_media_b64("https://third-party.example/audio.mp3")
        assert result is not None
        data, mime = result
        assert mime == "audio/mpeg"
        import base64
        assert base64.b64decode(data) == b"fake-remote-bytes"


class TestInlineMediaEndpoint:
    def test_resolves_local_upload(self, client, uploaded_image):
        response = client.get(
            "/api/inline-media", params={"url": "/uploads/images/sample.png"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["dataUrl"].startswith("data:image/png;base64,")

    def test_404_for_missing_file(self, client, uploaded_image):
        response = client.get(
            "/api/inline-media", params={"url": "/uploads/images/nope.png"}
        )
        assert response.status_code == 404

    def test_404_for_path_traversal(self, client, uploaded_image):
        response = client.get(
            "/api/inline-media", params={"url": "/uploads/../../etc/passwd"}
        )
        assert response.status_code == 404
