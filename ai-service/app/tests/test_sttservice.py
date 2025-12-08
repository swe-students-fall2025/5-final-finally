from unittest.mock import patch, MagicMock
from app.services import stt_service

def test_get_model_cached():
    with patch("app.services.stt_service.WhisperModel") as MockModel:
        model1 = stt_service.get_model()
        model2 = stt_service.get_model()

    # Must be same cached instance
    assert model1 is model2

def test_transcribe_audio():
    fake_model = MagicMock()
    fake_segment = MagicMock()
    fake_segment.text = "hello world"
    fake_model.transcribe.return_value = ([fake_segment], None)

    with patch("app.services.stt_service.get_model", return_value=fake_model):
        text = stt_service.transcribe_audio("fakefile.wav")

    assert text == "hello world"
