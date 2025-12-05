import os
import tempfile
from pathlib import Path
from typing import List, Dict

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from pydantic import BaseModel

# Assuming these modules exist and are correct
from app.db import create_or_get_conversation, append_message, conversations 
from app.services.stt_service import transcribe_audio
from .gemini_client import generate_cheerful_reply


# ========= Pydantic Models =========

class ChatRequest(BaseModel):
    user_id: str
    text: str


class ChatResponse(BaseModel):
    reply: str
    history: List[Dict]


# ========= FastAPI app =========

app = FastAPI()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """
    Text-only chat endpoint:
    - JSON: { "user_id": "...", "text": "..." }
    - Generate a cheerful reply using Gemini
    - Write user/AI messages to Mongo and return the full history
    """
    # 1. Find or create "today's" active conversation
    conv = create_or_get_conversation(req.user_id)

    # 2. Write the user message to MongoDB first
    append_message(conv["_id"], "user", req.text)

    # 3. Generate AI reply (Gemini cheerful)
    ai_reply = generate_cheerful_reply(req.text)

    # 4. Write the AI message to MongoDB as well
    append_message(conv["_id"], "ai", ai_reply)

    # 5. Query the latest conversation again to get the full messages array
    updated_conv = conversations.find_one({"_id": conv["_id"]})

    # 6. Return AI reply + full conversation history
    return ChatResponse(
        reply=ai_reply,
        history=updated_conv["messages"],
    )


@app.post("/api/chat/audio", response_model=ChatResponse)
async def chat_audio(
    user_id: str = Query(..., description="Current user id"),
    file: UploadFile = File(...),
):
    """
    Audio chat endpoint:

    Flask client invocation example:
      POST http://localhost:8001/api/chat/audio?user_id=...
      Content-Type: multipart/form-data
      files["file"] = audio_file

    The process flow here is:
      1. Save the uploaded audio to a temporary file.
      2. Call faster-whisper to transcribe to text.
      3. Call Gemini to generate a cheerful reply.
      4. Write user/AI messages to Mongo conversation history.
      5. Return { reply, history } to the Flask client.
    """
    # 0. Simple validation
    if not user_id:
        raise HTTPException(status_code=400, detail="Missing user_id")

    # 1. Write the uploaded file to a temporary file (WhisperModel requires a file path)
    try:
        suffix = Path(file.filename or "").suffix or ".wav"
    except Exception:
        suffix = ".wav"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        raw = await file.read()
        tmp.write(raw)
        tmp_path = tmp.name

    # 2. Transcribe audio using faster-whisper
    try:
        user_text = transcribe_audio(tmp_path)
    except Exception as e:
        # Clean up the temporary file on error
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")
    finally:
        # Delete the temporary file after transcription to prevent disk accumulation
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    if not user_text:
        user_text = "(empty transcription)"

    # 3. Similar to /api/chat, write user/AI messages to Mongo
    conv = create_or_get_conversation(user_id)
    append_message(conv["_id"], "user", user_text)

    # ⭐ Generate cheerful reply using Gemini
    ai_reply = generate_cheerful_reply(user_text)
    append_message(conv["_id"], "ai", ai_reply)

    # 4. Fetch the latest history
    updated_conv = conversations.find_one({"_id": conv["_id"]})

    # 5. Return to Flask client
    return ChatResponse(
        reply=ai_reply,
        history=updated_conv["messages"],
    )