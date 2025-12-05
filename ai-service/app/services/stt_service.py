from pathlib import Path
from typing import Union

from faster_whisper import WhisperModel

# Lazily load the global model to avoid reloading on every request
_model: WhisperModel | None = None


def get_model() -> WhisperModel:
    global _model
    if _model is None:
        # Start with the tiny/cpu version for speed and low resource usage
        # Can be switched to "base" / "small" later
        _model = WhisperModel("tiny", device="cpu", compute_type="float32")
    return _model


def transcribe_audio(path: Union[str, Path]) -> str:
    """
    Given an audio file path, returns the recognized text (simply concatenating all segments).
    """
    model = get_model()
    audio_path = str(path)

    segments, info = model.transcribe(audio_path)

    pieces: list[str] = []
    for seg in segments:
        # seg.text is already the result for this segment, e.g., " I went for a run today"
        pieces.append(seg.text)

    text = " ".join(pieces).strip()
    return text