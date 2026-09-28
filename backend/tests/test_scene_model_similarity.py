"""The student app's "similar to the model voice" score rides along with each
submitted scene. It is optional, bounded 0-100, and stored as-is."""

import os
import sys

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.schemas.models import SceneSubmission


def test_model_similarity_is_kept_in_the_stored_scene():
    scene = SceneSubmission(sceneIndex=0, modelSimilarity=76)
    assert scene.model_dump()["modelSimilarity"] == 76


def test_model_similarity_is_optional_for_older_clients():
    assert SceneSubmission(sceneIndex=0).model_dump()["modelSimilarity"] is None


@pytest.mark.parametrize("value", [-1, 101])
def test_model_similarity_out_of_range_is_rejected(value):
    with pytest.raises(ValidationError):
        SceneSubmission(sceneIndex=0, modelSimilarity=value)
