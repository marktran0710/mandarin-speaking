from typing import List

from fastapi import APIRouter
from pydantic import BaseModel, Field

from pinyin_service import canonical_pinyin

router = APIRouter()


class PinyinBatchRequest(BaseModel):
    texts: List[str] = Field(default_factory=list, max_length=500)


@router.post("/api/pinyin")
def resolve_pinyin(request: PinyinBatchRequest):
    """Resolve frontend pinyin requests through the backend canonical map."""
    seen: set[str] = set()
    items = []
    for raw_text in request.texts:
        text = str(raw_text or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        items.append({"text": text, "pinyin": canonical_pinyin(text)})
    return {"source": "backend.taiwan_pinyin", "items": items}
