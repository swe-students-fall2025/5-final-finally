# Final Project

An exercise to put to practice software development teamwork, subsystem communication, containers, deployment, and CI/CD pipelines. See [instructions](./instructions.md) for details.

# AI Diary System

## 📋 Project Overview

An AI-powered intelligent diary system that supports **voice recording**, **real-time conversation**, and **automatic diary generation**. Users can interact with AI through natural language, and the system automatically generates structured diary entries from conversations.

### Core Features
- 🎙️ **Real-time Voice Recording**: Browser-based audio recording and upload
- 💬 **AI Conversation**: Warm and cheerful responses powered by Gemini Flash
- 📝 **Automatic Diary Generation**: Extract key information from conversations to create diary entries
- 📊 **Emotion Analysis**: Automatically identify and tag daily emotions (mood & mood_score)
- 🔐 **User Isolation**: Complete user authentication and session management system

---

## 🔄 Complete Data Flow

### 1️⃣ User Initiates Conversation
```
User clicks "Start Recording" 
    → Browser captures audio 
    → POST /api/conversations/<cid>/audio
```

### 2️⃣ Web-App Processes Request
```python
@app.route('/api/conversations/<cid>/audio', methods=['POST'])
def handle_audio():
    # 1. Verify user identity
    # 2. Forward audio to ai-service
    response = requests.post(
        'http://ai-service:8001/api/chat/audio',
        files={'audio': audio_file}
    )
    # 3. Save conversation to diary_db.conversations
    # 4. Return AI reply to frontend
```

### 3️⃣ AI-Service Processes Audio
```python
@app.post('/api/chat/audio')
async def chat_audio(audio: UploadFile):
    # 1. Faster-Whisper speech-to-text
    text = transcribe_audio(audio)
    
    # 2. Load history from ai_diary.conversations
    history = load_conversation_history(user_id, date)
    
    # 3. Gemini Flash generates reply
    reply = generate_cheerful_reply(text, history)
    
    # 4. Update ai_diary.conversations (cache)
    save_to_ai_context(user_id, date, text, reply)
    
    # 5. Return reply to web-app
    return {"reply": reply, "transcript": text}
```

### 4️⃣ Generate Diary
```
User clicks "Complete Conversation"
    → POST /api/conversations/<cid>/complete
    → Web-App calls ai-service to analyze conversation
    → Generate structured diary (title, summary, mood, content)
    → Save to diary_db.diaries
    → Display diary on frontend
```

---

## 🗄️ Database Design

### Database 1: `diary_db` (Main Application Database)

> **Purpose**: Stores all user-visible data, serves as the single source of truth for the system

#### Collection: `users`
```javascript
{
  "_id": ObjectId("..."),
  "username": "alice",
  "password": "hashed_password",
  "created_at": ISODate("2024-01-01T00:00:00Z")
}
```

#### Collection: `conversations`
```javascript
{
  "_id": ObjectId("..."),
  "user_id": ObjectId("..."),
  "date": "2024-12-05",
  "messages": [
    {
      "role": "user",
      "content": "Went for a walk in the park today",
      "timestamp": ISODate("...")
    },
    {
      "role": "assistant",
      "content": "That sounds lovely! How was the weather?",
      "timestamp": ISODate("...")
    }
  ],
  "created_at": ISODate("..."),
  "completed": false
}
```

#### Collection: `diaries`
```javascript
{
  "_id": ObjectId("..."),
  "user_id": ObjectId("..."),
  "conversation_id": ObjectId("..."),
  "date": "2024-12-05",
  "time": "14:30",
  "title": "Winter Walk in the Park",
  "content": "The weather was beautiful today...",
  "summary": "Took a walk in the park, enjoyed the winter sunshine",
  "mood": "peaceful",
  "mood_score": 8,
  "created_at": ISODate("...")
}
```

---

### Database 2: `ai_diary` (AI Internal Context Store)

> **Purpose**: Private database for AI service, maintains conversation history for generating replies

#### Collection: `conversations`
```javascript
{
  "_id": ObjectId("..."),
  "user_id": "alice",  // String, not ObjectId
  "date": "2024-12-05",
  "messages": [
    {
      "role": "user",
      "content": "Went for a walk in the park today"
    },
    {
      "role": "assistant",
      "content": "That sounds lovely! How was the weather?"
    }
  ],
  "updated_at": ISODate("...")
}
```

**⚠️ Important Notes**:
- `ai_diary` is used only internally by AI service
- Does not store diary metadata (such as mood, summary)
- Not directly accessed by Web-App
- One active conversation per user per day
- Serves as LLM context cache to improve response speed