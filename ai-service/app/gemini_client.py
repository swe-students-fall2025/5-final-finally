import google.generativeai as genai
from .config import GEMINI_API_KEY
import json

genai.configure(api_key=GEMINI_API_KEY)


def generate_cheerful_reply(user_text: str) -> str:
    prompt = f"""
    You are a cheerful, warm, slightly humorous diary assistant.
    Respond casually and kindly, as if comforting a friend.
    The user said: "{user_text}"

    Reply in a friendly and supportive tone, 1–3 sentences, no emojis.
    """

    model = genai.GenerativeModel("gemini-2.0-flash-lite")
    response = model.generate_content(prompt)
    return response.text.strip()


def generate_diary(messages: list) -> dict:
    """
    Generate a diary entry based on conversation messages.
    Args:
        messages: List of message map with 'role' ('user'/'ai') and 'text' keys
    Returns:
        dict with 'title', 'content', 'summary', 'mood', 'mood_score'
    """
    # Format conversation history
    conversation_text = ""
    for msg in messages:
        role = "Me" if msg.get("role") == "user" else "AI Assistant"
        text = msg.get("text", "")
        conversation_text += f"{role}: {text}\n"

    prompt = f"""
You are a professional diary writing assistant. Based on the following conversation between a user and an AI assistant, generate a warm, personal first-person diary entry.

Requirements:
1. Write in first person ("I")
2. Extract key events, emotions, and feelings from the conversation
3. Do NOT simply repeat the conversation - write it like a real diary with reflection and emotion
4. Use natural, flowing language as if written by a real person
5. Length: 150-300 words
6. Generate an appropriate diary title
7. Generate a brief summary (1-2 sentences)
8. Analyze the overall mood: must be one of "positive", "negative", or "neutral"
9. Provide a mood_score: positive number for positive mood, negative for negative, 0 for neutral (range: -5 to 5)

Conversation:
{conversation_text}

Respond ONLY with valid JSON in this exact format (no markdown, no extra text):
{{"title": "Diary Title Here", "content": "Full diary content here...", "summary": "Brief 1-2 sentence summary", "mood": "positive", "mood_score": 2}}
"""

    model = genai.GenerativeModel("gemini-2.0-flash-lite")
    response = model.generate_content(prompt)

    # Parse response
    try:
        text = response.text.strip()

        # Remove markdown code blocks if present
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line (```json) and last line (```)
            text = "\n".join(lines[1:-1])
        text = text.strip()

        result = json.loads(text)

        # Validate mood value
        mood = result.get("mood", "neutral").lower()
        if mood not in ["positive", "negative", "neutral"]:
            mood = "neutral"

        # Validate mood_score
        try:
            mood_score = int(result.get("mood_score", 0))
            mood_score = max(-5, min(5, mood_score))  # Clamp to range
        except (ValueError, TypeError):
            mood_score = 0

        return {
            "title": result.get("title", "Today's Diary"),
            "content": result.get("content", ""),
            "summary": result.get("summary", ""),
            "mood": mood,
            "mood_score": mood_score,
        }

    except (json.JSONDecodeError, KeyError, AttributeError):
        # Fallback if JSON parsing fails
        return {
            "title": "Today's Diary",
            "content": (
                response.text.strip() if response.text else "Had a conversation today."
            ),
            "summary": "A diary entry from today's conversation.",
            "mood": "neutral",
            "mood_score": 0,
        }
