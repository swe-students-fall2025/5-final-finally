from unittest.mock import patch, MagicMock
from app import gemini_client

def test_generate_cheerful_reply():
    mock_model = MagicMock()
    mock_model.generate_content.return_value.text = "mock reply"

    with patch("app.gemini_client.genai.GenerativeModel", return_value=mock_model):
        reply = gemini_client.generate_cheerful_reply("hi")

    assert reply == "mock reply"

def test_generate_diary_json_ok():
    mock_model = MagicMock()
    mock_model.generate_content.return_value.text = (
        '{"title": "T", "content": "C", "summary": "S", "mood": "positive", "mood_score": 2}'
    )

    with patch("app.gemini_client.genai.GenerativeModel", return_value=mock_model):
        result = gemini_client.generate_diary([{"role": "user", "text": "hello"}])

    assert result["title"] == "T"
    assert result["mood_score"] == 2

def test_generate_diary_fallback():
    mock_model = MagicMock()
    mock_model.generate_content.return_value.text = "INVALID JSON"

    with patch("app.gemini_client.genai.GenerativeModel", return_value=mock_model):
        res = gemini_client.generate_diary([{"role": "user", "text": "hi"}])

    assert res["title"] == "Today's Diary"
    assert res["mood"] == "neutral"
