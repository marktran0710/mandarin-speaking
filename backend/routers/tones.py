from fastapi import APIRouter, HTTPException

from chinese_tones import get_reference_tone_pattern
from main import ReferenceToneResponse

router = APIRouter()


@router.get("/api/reference-tone/{tone_number}", response_model=ReferenceToneResponse)
async def get_reference_tone(tone_number: int):
    """
    Get reference pitch contour for a Mandarin tone (1-4).
    """
    if tone_number not in [1, 2, 3, 4]:
        raise HTTPException(
            status_code=400,
            detail="Tone number must be 1, 2, 3, or 4"
        )

    ref = get_reference_tone_pattern(tone_number)

    if not ref:
        raise HTTPException(status_code=404, detail="Tone reference not found")

    return ReferenceToneResponse(
        tone=ref["tone"],
        name=ref["name"],
        character=ref["character"],
        pinyin=ref["pinyin"],
        description=ref["description"],
        pitch_pattern=ref["pitch_pattern"],
        frequency_range=ref["frequency_range"],
        expected_mean=ref["expected_mean"],
    )


@router.get("/api/all-tones")
async def get_all_tones():
    """
    Get all Mandarin tone references.
    """
    tones = {}
    for tone_num in [1, 2, 3, 4]:
        ref = get_reference_tone_pattern(tone_num)
        tones[tone_num] = ref

    return tones
