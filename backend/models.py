"""Shared Pydantic request/response models."""
from pydantic import BaseModel, Field
from typing import List, Optional, Tuple


class TranscriptionResponse(BaseModel):
    text: str
    model: str


class AnalysisResponse(BaseModel):
    description: str = ""
    transcription: str = ""
    transcription_model: str = ""
    pitch_contour: List[Tuple[float, float]]
    word_prosody: List[dict]
    detected_tone: int
    tone_accuracy: float
    formants: dict
    vowel_quality: str = ""
    speech_rate: float
    fluency_score: float
    pitch_statistics: dict
    tone_direction: str = ""
    pause_analysis: dict = {}
    feedback: str
    ai_feedback: dict


class AsrStatusResponse(BaseModel):
    provider: str
    status: str
    message: str


class ReferenceToneResponse(BaseModel):
    tone: int
    name: str
    character: str
    pinyin: str
    description: str
    pitch_pattern: List[float]
    frequency_range: Tuple[int, int]
    expected_mean: int


class StoryImageGenerationRequest(BaseModel):
    situation: str
    level: str = "Beginner speaking"
    style: str = "warm educational comic"
    language_focus: str = "Mandarin story speaking with who, where, event, problem, solution, and feeling"


class StoryImageFrame(BaseModel):
    index: int
    title: str
    student_prompt: str
    vocabulary: List[str]
    image_prompt: str
    image_url: str


class StoryImageGenerationResponse(BaseModel):
    provider: str
    title: str
    learning_goal: str
    frames: List[StoryImageFrame]


class AudioRecordRequest(BaseModel):
    id: str
    timestamp: str
    duration: int
    transcription: str = ""
    model: str
    topicId: Optional[str] = None
    imageUrl: Optional[str] = None
    imageIndex: Optional[int] = None
    audioUrl: Optional[str] = None
    praatMetrics: Optional[dict] = None


class CustomStoryFrameRequest(BaseModel):
    imageUrl: str
    prompt: str
    vocabulary: str = ""
    vocabularyGroups: Optional[List[dict]] = None


class CustomStoryRequest(BaseModel):
    id: str
    title: str
    learningGoal: str
    level: str
    frames: List[CustomStoryFrameRequest]
    published: bool = False


class HelpRequest(BaseModel):
    id: str = Field(..., max_length=128)
    studentName: str = Field(default="Student", max_length=100)
    message: str = Field(default="I need teacher help.", max_length=500)
    status: str = "open"
    createdAt: str
    resolvedAt: Optional[str] = None
