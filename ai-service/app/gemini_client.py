import google.generativeai as genai
from .config import GEMINI_API_KEY

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
