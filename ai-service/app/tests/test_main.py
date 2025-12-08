import io
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from app.main import app

client = TestClient(app)

# -------------------------------------------------------------------
# 1. /health
# -------------------------------------------------------------------

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# -------------------------------------------------------------------
# 2. /api/chat (text) — mock Mongo + Gemini
# -------------------------------------------------------------------

@patch("app.main.append_message")
@patch("app.main.create_or_get_conversation")
@patch("app.main.generate_cheerful_reply")
def test_chat_text(mock_reply, mock_get_conv, mock_append):
    mock_get_conv.return_value = {"_id": "conv123"}
    mock_reply.return_value = "MOCK_AI_REPLY"

    with patch("app.main.conversations.find_one") as mock_find:
        mock_find.return_value = {
            "_id": "conv123",
            "messages": [
                {"role": "user", "text": "Hello"},
                {"role": "ai", "text": "MOCK_AI_REPLY"}
            ]
        }

        payload = {"user_id": "u1", "text": "Hello"}
        r = client.post("/api/chat", json=payload)

    assert r.status_code == 200
    data = r.json()

    assert data["reply"] == "MOCK_AI_REPLY"
    assert len(data["history"]) == 2


# -------------------------------------------------------------------
# 3. /api/chat/audio — mock Whisper + Mongo + Gemini
# -------------------------------------------------------------------

@patch("app.main.append_message")
@patch("app.main.create_or_get_conversation")
@patch("app.main.generate_cheerful_reply")
@patch("app.main.transcribe_audio")
def test_chat_audio(mock_stt, mock_reply, mock_get_conv, mock_append):

    mock_stt.return_value = "USER SAID SOMETHING"
    mock_reply.return_value = "MOCK_AUDIO_REPLY"
    mock_get_conv.return_value = {"_id": "c001"}

    with patch("app.main.conversations.find_one") as mock_find:
        mock_find.return_value = {
            "_id": "c001",
            "messages": [
                {"role": "user", "text": "USER SAID SOMETHING"},
                {"role": "ai", "text": "MOCK_AUDIO_REPLY"},
            ],
        }

        fake_audio = io.BytesIO(b"fake audio")
        r = client.post(
            "/api/chat/audio?user_id=u1",
            files={"file": ("test.wav", fake_audio, "audio/wav")},
        )

    assert r.status_code == 200
    data = r.json()
    assert data["reply"] == "MOCK_AUDIO_REPLY"
    assert len(data["history"]) == 2


# -------------------------------------------------------------------
# 4. /api/chat/audio — STT error branch
# -------------------------------------------------------------------

@patch("app.main.transcribe_audio")
def test_chat_audio_stt_error(mock_stt):
    mock_stt.side_effect = Exception("STT FAILED")

    fake_audio = io.BytesIO(b"fake")
    r = client.post(
        "/api/chat/audio?user_id=u1",
        files={"file": ("x.wav", fake_audio, "audio/wav")},
    )

    assert r.status_code == 500
    assert "Transcription failed" in r.json()["detail"]


# -------------------------------------------------------------------
# 5. /api/transcribe — success
# -------------------------------------------------------------------

@patch("app.main.transcribe_audio")
def test_transcribe_ok(mock_stt):
    mock_stt.return_value = "HELLO WORLD"

    fake_audio = io.BytesIO(b"123")
    r = client.post(
        "/api/transcribe",
        files={"file": ("a.wav", fake_audio, "audio/wav")},
    )

    assert r.status_code == 200
    assert r.json()["text"] == "HELLO WORLD"


# -------------------------------------------------------------------
# 6. /api/transcribe — STT exception
# -------------------------------------------------------------------

@patch("app.main.transcribe_audio")
def test_transcribe_error(mock_stt):
    mock_stt.side_effect = Exception("BAD AUDIO")

    fake_audio = io.BytesIO(b"123")
    r = client.post(
        "/api/transcribe",
        files={"file": ("a.wav", fake_audio, "audio/wav")},
    )

    assert r.status_code == 500
    assert "Transcription failed" in r.json()["detail"]


# -------------------------------------------------------------------
# 7. /api/generate-diary — success case
# -------------------------------------------------------------------

@patch("app.main.generate_diary")
def test_generate_diary_ok(mock_diary):
    mock_diary.return_value = {
        "title": "MOCK TITLE",
        "content": "MOCK CONTENT",
        "summary": "MOCK SUMMARY",
        "mood": "positive",
        "mood_score": 4,
    }

    payload = {
        "messages": [
            {"role": "user", "text": "hi"},
            {"role": "ai", "text": "hello"},
        ],
        "preferences": {"theme": "daily", "style": "casual"},
    }

    r = client.post("/api/generate-diary", json=payload)
    assert r.status_code == 200

    data = r.json()
    assert data["title"] == "MOCK TITLE"
    assert data["mood_score"] == 4


# -------------------------------------------------------------------
# 8. /api/generate-diary — no messages (400)
# -------------------------------------------------------------------

def test_generate_diary_no_messages():
    r = client.post("/api/generate-diary", json={"messages": []})
    assert r.status_code == 400


# -------------------------------------------------------------------
# 9. /api/generate-diary — no user messages (400)
# -------------------------------------------------------------------

def test_generate_diary_no_user_message():
    payload = {
        "messages": [{"role": "ai", "text": "hi"}]
    }
    r = client.post("/api/generate-diary", json=payload)
    assert r.status_code == 400
