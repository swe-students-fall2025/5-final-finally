from flask import (
    Flask,
    jsonify,
    request,
    render_template,
    session,
    redirect,
    url_for,
)
from bson import ObjectId
from pymongo import MongoClient
from datetime import datetime
from zoneinfo import ZoneInfo
import requests
import os

AI_SERVICE_BASE = os.environ.get("AI_SERVICE_URL", "http://localhost:8001")

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
client = MongoClient(MONGO_URI)
db = client["diary_db"]


app = Flask(__name__)
app.secret_key = "dev-secret-key"


# ----------------------------
# Mood + summary heuristics
# ----------------------------

POSITIVE_WORDS = {
    "happy",
    "great",
    "good",
    "excited",
    "relaxed",
    "fun",
    "love",
    "enjoy",
    "amazing",
    "wonderful",
}

NEGATIVE_WORDS = {
    "sad",
    "tired",
    "exhausted",
    "stress",
    "stressed",
    "anxious",
    "anxiety",
    "angry",
    "upset",
    "bad",
    "worried",
    "frustrated",
    "depressed",
}


def analyze_mood_and_summary(user_texts):
    full = " ".join(user_texts).lower()
    pos = sum(full.count(w) for w in POSITIVE_WORDS)
    neg = sum(full.count(w) for w in NEGATIVE_WORDS)
    score = pos - neg

    if score > 1:
        mood = "positive"
    elif score < -1:
        mood = "negative"
        # “neutral” spelled normally
    else:
        mood = "neutral"

    if user_texts:
        summary = user_texts[0].strip()
        if len(summary) > 220:
            summary = summary[:217] + "..."
    else:
        summary = "You had a short conversation with your AI diary today."

    if "exam" in full or "test" in full:
        title = "Thinking about exams"
    elif "travel" in full or "trip" in full:
        title = "Thinking about a trip"
    elif mood == "positive":
        title = "A good day"
    elif mood == "negative":
        title = "A tough day"
    else:
        title = "A regular day"

    return {
        "title": title,
        "summary": summary,
        "mood": mood,
        "mood_score": score,
    }


# ----------------------------
# Auth
# ----------------------------


@app.route("/")
def root():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if "user_id" in session:
            return redirect(url_for("home"))
        return render_template("login.html")

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    if not username or not password:
        return render_template("login.html", error="Missing fields.", username=username)

    users = db.users
    user = users.find_one({"username": username})

    if user:
        if user.get("password") != password:
            return render_template(
                "login.html", error="Wrong password.", username=username
            )
    else:
        uid = users.insert_one({"username": username, "password": password}).inserted_id
        user = users.find_one({"_id": uid})

    session["user_id"] = str(user["_id"])
    session["username"] = user["username"]
    return redirect(url_for("home"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/home")
def home():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template(
        "index.html", user_id=session["user_id"], username=session["username"]
    )


# ----------------------------
# Conversations
# ----------------------------


@app.route("/api/conversations", methods=["POST"])
def start_conversation():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    uid = ObjectId(session["user_id"])

    doc = {
        "user_id": uid,
        "created_at": datetime.utcnow(),
        "messages": [],
        "status": "active",
    }
    r = db.conversations.insert_one(doc)
    cid = str(r.inserted_id)

    greeting = "Hi! How was your day?"
    db.conversations.update_one(
        {"_id": r.inserted_id},
        {"$push": {"messages": {"role": "ai", "text": greeting}}},
    )

    return jsonify({"conversation_id": cid, "first_message": greeting})


@app.route("/api/conversations/<cid>/messages", methods=["POST"])
def add_message(cid):
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    try:
        oid = ObjectId(cid)
    except:
        return jsonify({"error": "Invalid id"}), 400

    conv = db.conversations.find_one({"_id": oid})
    if not conv:
        return jsonify({"error": "Not found"}), 404
    if str(conv["user_id"]) != session["user_id"]:
        return jsonify({"error": "Forbidden"}), 403

    # 1. Get user input from frontend (Minimal version: Frontend sends JSON { "text": "..." })
    data = request.get_json() or {}
    user_msg = data.get("text", "").strip()

    if not user_msg:
        # If the frontend isn't ready yet, you can keep a default placeholder
        user_msg = "This is a placeholder transcription of your audio."

    # 2. Call ai-service's /api/chat to get AI reply
    ai_msg = "Thanks for sharing! Tell me more about your day."  # fallback

    try:
        payload = {
            "user_id": session["user_id"],  # Use the current logged-in user ID
            "text": user_msg,
        }
        r = requests.post(f"{AI_SERVICE_BASE}/api/chat", json=payload, timeout=10)
        if r.status_code == 200:
            data = r.json()
            ai_msg = data.get("reply", ai_msg)
        else:
            # Log the error here for future debugging
            print("AI-service error:", r.status_code, r.text)
    except Exception as e:
        # If ai-service is down, fallback to default text to ensure user experience
        print("Error calling ai-service:", e)

    # 3. As before: push both user + ai messages to the current conversation
    db.conversations.update_one(
        {"_id": oid},
        {
            "$push": {
                "messages": {
                    "$each": [
                        {"role": "user", "text": user_msg},
                        {"role": "ai", "text": ai_msg},
                    ]
                }
            }
        },
    )

    return jsonify({"user_message": user_msg, "ai_response": ai_msg})


@app.route("/api/conversations/<cid>/audio", methods=["POST"])
def add_audio_message(cid):
    """
    Audio version of add_message:

    Frontend: POST /api/conversations/<cid>/audio
      - Content-Type: multipart/form-data
      - Fields:
          audio: Audio file (required)

    Flask logic:
      1. Check login & conversation ownership.
      2. Retrieve the file and forward it to ai-service /api/chat/audio.
      3. Extract the transcribed text + AI reply from the ai-service response.
      4. Write to diary_db.conversations for the current conversation.
      5. Return results to the frontend.
    """
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    # Validate conversation ID
    try:
        oid = ObjectId(cid)
    except Exception:
        return jsonify({"error": "Invalid id"}), 400

    conv = db.conversations.find_one({"_id": oid})
    if not conv:
        return jsonify({"error": "Not found"}), 404
    if str(conv["user_id"]) != session["user_id"]:
        return jsonify({"error": "Forbidden"}), 403

    # 1. Retrieve audio file from form data (frontend field name is "audio")
    file = request.files.get("audio")
    if file is None or file.filename == "":
        return jsonify({"error": "No audio file uploaded"}), 400

    # 2. Call ai-service's /api/chat/audio
    user_msg = "This is a placeholder transcription of your audio."
    ai_msg = "Thanks for sharing! Tell me more about your day."

    try:
        # per ai-service convention: pass user_id as query param, file field in files is named "file"
        files = {"file": (file.filename, file.stream, file.mimetype or "audio/wav")}
        params = {"user_id": session["user_id"]}

        r = requests.post(
            f"{AI_SERVICE_BASE}/api/chat/audio",
            params=params,
            files=files,
            timeout=60,
        )

        if r.status_code == 200:
            data = r.json()
            ai_msg = data.get("reply", ai_msg)

            # Find the "last user message" in history to treat as the transcribed text
            history = data.get("history", [])
            for m in reversed(history):
                if m.get("role") == "user":
                    user_msg = m.get("text", user_msg)
                    break
        else:
            print("AI-service audio error:", r.status_code, r.text)
    except Exception as e:
        print("Error calling ai-service audio endpoint:", e)

    # 3. Same as text endpoint: push both user + ai messages to diary_db.conversations
    db.conversations.update_one(
        {"_id": oid},
        {
            "$push": {
                "messages": {
                    "$each": [
                        {"role": "user", "text": user_msg},
                        {"role": "ai", "text": ai_msg},
                    ]
                }
            }
        },
    )

    # 4. Return to frontend
    return jsonify(
        {
            "user_message": user_msg,
            "ai_response": ai_msg,
        }
    )


@app.route("/api/transcribe", methods=["POST"])
def transcribe_audio():
    """
    Transcribe audio to text without chat.
    Used for voice input of diary preferences.
    """
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    file = request.files.get("audio")
    if file is None or file.filename == "":
        return jsonify({"error": "No audio file uploaded"}), 400

    text = ""

    try:
        files = {"file": (file.filename, file.stream, file.mimetype or "audio/wav")}

        r = requests.post(
            f"{AI_SERVICE_BASE}/api/transcribe",
            files=files,
            timeout=60,
        )

        if r.status_code == 200:
            data = r.json()
            text = data.get("text", "")
        else:
            print("AI-service transcribe error:", r.status_code, r.text)
    except Exception as e:
        print("Error calling ai-service transcribe endpoint:", e)

    return jsonify({"text": text})


@app.route("/api/conversations/<cid>/complete", methods=["POST"])
def complete_conversation(cid):
    """Generate diary preview - does NOT save to database."""
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    try:
        oid = ObjectId(cid)
    except Exception:
        return jsonify({"error": "Invalid id"}), 400

    conv = db.conversations.find_one({"_id": oid})
    if not conv:
        return jsonify({"error": "Not found"}), 404
    if str(conv["user_id"]) != session["user_id"]:
        return jsonify({"error": "Forbidden"}), 403

    now = datetime.now(ZoneInfo("America/New_York"))
    today_str = now.strftime("%Y-%m-%d")

    msgs = conv.get("messages", [])
    data = request.get_json() or {}
    preferences = data.get("preferences", None)

    try:
        payload = {"messages": msgs}
        if preferences:
            payload["preferences"] = preferences

        r = requests.post(
            f"{AI_SERVICE_BASE}/api/generate-diary", json=payload, timeout=30
        )
        if r.status_code == 200:
            ai_diary = r.json()
            title = ai_diary["title"]
            content = ai_diary["content"]
            summary = ai_diary["summary"]
            mood = ai_diary["mood"]
            mood_score = ai_diary.get("mood_score", 0)
        else:
            raise Exception("AI service returned " + str(r.status_code))
    except Exception as e:
        print("Error calling ai-service for diary:", e)
        texts = [m["text"] for m in msgs if m.get("role") == "user"]
        analysis = analyze_mood_and_summary(texts)
        title = analysis["title"]
        content = (
            "\n".join(texts)
            if texts
            else "You had a short chat with your AI diary today."
        )
        summary = analysis["summary"]
        mood = analysis["mood"]
        mood_score = analysis["mood_score"]

    # Return preview only - NOT saved to database yet
    return jsonify(
        {
            "conversation_id": cid,
            "title": title,
            "content": content,
            "summary": summary,
            "mood": mood,
            "mood_score": mood_score,
            "suggested_date": today_str,
        }
    )


@app.route("/api/conversations/<cid>/save", methods=["POST"])
def save_diary(cid):
    """Save the edited diary to database."""
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    try:
        oid = ObjectId(cid)
    except Exception:
        return jsonify({"error": "Invalid id"}), 400

    conv = db.conversations.find_one({"_id": oid})
    if not conv:
        return jsonify({"error": "Not found"}), 404
    if str(conv["user_id"]) != session["user_id"]:
        return jsonify({"error": "Forbidden"}), 403

    uid = conv["user_id"]
    now = datetime.now(ZoneInfo("America/New_York"))
    created_date = now.strftime("%Y-%m-%d")
    created_time = now.strftime("%H:%M")

    data = request.get_json() or {}
    title = data.get("title", "Untitled")
    content = data.get("content", "")
    mood = data.get("mood", "neutral")
    mood_score = data.get("mood_score", 0)
    entry_date = data.get("entry_date", created_date)

    # Validate entry_date format
    try:
        datetime.strptime(entry_date, "%Y-%m-%d")
    except ValueError:
        entry_date = created_date

    diary = {
        "user_id": uid,
        "entry_date": entry_date,
        "created_date": created_date,
        "created_time": created_time,
        "title": title,
        "content": content,
        "summary": content[:200] if content else "",
        "mood": mood,
        "mood_score": mood_score,
        "created_at": now,
        "conversation_id": oid,
    }

    new_id = db.diaries.insert_one(diary).inserted_id

    db.conversations.update_one({"_id": oid}, {"$set": {"status": "completed"}})

    return jsonify(
        {
            "diary_id": str(new_id),
            "entry_date": entry_date,
            "created_date": created_date,
            "created_time": created_time,
            "title": title,
            "content": content,
            "mood": mood,
            "mood_score": mood_score,
        }
    )


# ----------------------------
# Diaries: list / detail / search / edit / delete
# ----------------------------
@app.route("/api/users/<uid>/diaries/calendar")
def get_calendar_diaries(uid):
    """Get diaries grouped by date for calendar view."""
    if "user_id" not in session or session["user_id"] != uid:
        return jsonify({"error": "Forbidden"}), 403

    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)

    if not year or not month:
        now = datetime.now(ZoneInfo("America/New_York"))
        year = year or now.year
        month = month or now.month

    # Build date range for the month
    start_date = f"{year}-{month:02d}-01"
    if month == 12:
        end_date = f"{year + 1}-01-01"
    else:
        end_date = f"{year}-{month + 1:02d}-01"

    # Query diaries for this month
    cur = db.diaries.find(
        {
            "user_id": ObjectId(uid),
            "$or": [
                {"entry_date": {"$gte": start_date, "$lt": end_date}},
                {"date": {"$gte": start_date, "$lt": end_date}},
            ],
        }
    )

    diaries_by_date = {}
    for d in cur:
        # Support both old (date) and new (entry_date) format
        entry_date = d.get("entry_date") or d.get("date")
        if not entry_date:
            continue

        if entry_date not in diaries_by_date:
            diaries_by_date[entry_date] = []

        diaries_by_date[entry_date].append(
            {
                "diary_id": str(d["_id"]),
                "title": d.get("title", ""),
                "mood": d.get("mood", "neutral"),
                "preview": d.get("summary") or d.get("content", "")[:80],
            }
        )

    return jsonify(
        {
            "year": year,
            "month": month,
            "diaries_by_date": diaries_by_date,
        }
    )


@app.route("/api/users/<uid>/diaries")
def list_diaries(uid):
    if "user_id" not in session or session["user_id"] != uid:
        return jsonify({"error": "Forbidden"}), 403

    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 10))
    skip = (page - 1) * limit

    cur = (
        db.diaries.find({"user_id": ObjectId(uid)})
        .sort("entry_date", -1)
        .skip(skip)
        .limit(limit)
    )

    arr = []
    for d in cur:
        # Support both old and new date format
        entry_date = d.get("entry_date") or d.get("date")
        created_time = d.get("created_time") or d.get("time")

        arr.append(
            {
                "diary_id": str(d["_id"]),
                "entry_date": entry_date,
                "created_time": created_time,
                "title": d.get("title"),
                "preview": d.get("summary") or d.get("content", "")[:80],
                "mood": d.get("mood", "neutral"),
            }
        )

    total = db.diaries.count_documents({"user_id": ObjectId(uid)})

    return jsonify(
        {
            "diaries": arr,
            "total": total,
            "page": page,
            "pages": (total + limit - 1) // limit,
        }
    )


@app.route("/api/diaries/<diary_id>", methods=["GET", "PUT", "DELETE"])
def diary_detail(diary_id):
    try:
        oid = ObjectId(diary_id)
    except:
        return jsonify({"error": "Invalid id"}), 400

    doc = db.diaries.find_one({"_id": oid})
    if not doc:
        return jsonify({"error": "Not found"}), 404

    # Support both old and new date format
    entry_date = doc.get("entry_date") or doc.get("date")
    created_date = doc.get("created_date") or doc.get("date")
    created_time = doc.get("created_time") or doc.get("time")

    # GET
    if request.method == "GET":
        return jsonify(
            {
                "diary_id": str(doc["_id"]),
                "entry_date": entry_date,
                "created_date": created_date,
                "created_time": created_time,
                "title": doc.get("title"),
                "content": doc.get("content", ""),
                "summary": doc.get("summary", ""),
                "mood": doc.get("mood", "neutral"),
                "mood_score": doc.get("mood_score", 0),
            }
        )

    # PUT update
    if request.method == "PUT":
        data = request.get_json() or {}
        update_fields = {}

        if "content" in data:
            update_fields["content"] = data["content"]
        if "title" in data:
            update_fields["title"] = data["title"]
        if "entry_date" in data:
            update_fields["entry_date"] = data["entry_date"]
        if "mood" in data:
            update_fields["mood"] = data["mood"]
        if "mood_score" in data:
            update_fields["mood_score"] = data["mood_score"]

        if update_fields:
            db.diaries.update_one({"_id": oid}, {"$set": update_fields})
            doc.update(update_fields)

        # Re-fetch for response
        entry_date = doc.get("entry_date") or doc.get("date")
        created_date = doc.get("created_date") or doc.get("date")
        created_time = doc.get("created_time") or doc.get("time")

        return jsonify(
            {
                "diary_id": str(doc["_id"]),
                "entry_date": entry_date,
                "created_date": created_date,
                "created_time": created_time,
                "title": doc.get("title"),
                "content": doc.get("content", ""),
                "summary": doc.get("summary", ""),
                "mood": doc.get("mood", "neutral"),
                "mood_score": doc.get("mood_score", 0),
            }
        )

    # DELETE
    if request.method == "DELETE":
        db.diaries.delete_one({"_id": oid})
        return jsonify({"deleted": True})


@app.route("/api/users/<uid>/diaries/search")
def search_diaries(uid):
    if "user_id" not in session or session["user_id"] != uid:
        return jsonify({"error": "Forbidden"}), 403

    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"diaries": []})

    cur = (
        db.diaries.find(
            {
                "user_id": ObjectId(uid),
                "$or": [
                    {"title": {"$regex": q, "$options": "i"}},
                    {"content": {"$regex": q, "$options": "i"}},
                ],
            }
        )
        .sort("date", -1)
        .limit(30)
    )

    arr = []
    for d in cur:
        arr.append(
            {
                "diary_id": str(d["_id"]),
                "date": d.get("date"),
                "title": d.get("title"),
                "preview": d.get("summary") or d.get("content", "")[:80],
                "mood": d.get("mood", "neutral"),
            }
        )

    return jsonify({"diaries": arr})


if __name__ == "__main__":
    app.run(debug=True)
