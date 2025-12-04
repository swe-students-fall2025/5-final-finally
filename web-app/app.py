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

client = MongoClient("mongodb://localhost:27017/")
db = client["diary_db"]

app = Flask(__name__)
app.secret_key = "dev-secret-key"


# ----------------------------
# Mood + summary heuristics
# ----------------------------

POSITIVE_WORDS = {
    "happy", "great", "good", "excited", "relaxed",
    "fun", "love", "enjoy", "amazing", "wonderful",
}

NEGATIVE_WORDS = {
    "sad", "tired", "exhausted", "stress", "stressed",
    "anxious", "anxiety", "angry", "upset", "bad",
    "worried", "frustrated", "depressed",
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
            return render_template("login.html", error="Wrong password.", username=username)
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
    return render_template("index.html", user_id=session["user_id"], username=session["username"])


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
        {"$push": {"messages": {"role": "ai", "text": greeting}}}
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

    user_msg = "This is a placeholder transcription of your audio."
    ai_msg = "Thanks for sharing! Tell me more about your day."

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


@app.route("/api/conversations/<cid>/complete", methods=["POST"])
def complete_conversation(cid):
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
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    msgs = conv.get("messages", [])
    texts = [m["text"] for m in msgs if m.get("role") == "user"]

    analysis = analyze_mood_and_summary(texts)
    full = "\n".join(texts) if texts else "You had a short chat with your AI diary today."

    diary = {
        "user_id": uid,
        "date": date_str,
        "time": time_str,                 # ← 关键：这里一定要有
        "title": analysis["title"],
        "content": full,
        "summary": analysis["summary"],
        "mood": analysis["mood"],
        "mood_score": analysis["mood_score"],
        "created_at": now,
        "conversation_id": oid,
    }

    new_id = db.diaries.insert_one(diary).inserted_id

    db.conversations.update_one({"_id": oid}, {"$set": {"status": "completed"}})

    return jsonify({
        "diary_id": str(new_id),
        "date": diary["date"],
        "time": diary["time"],
        "title": diary["title"],
        "content": diary["content"],
        "summary": diary["summary"],
        "mood": diary["mood"],
        "mood_score": diary["mood_score"],
    })

# ----------------------------
# Diaries: list / detail / search / edit / delete
# ----------------------------

@app.route("/api/users/<uid>/diaries")
def list_diaries(uid):
    if "user_id" not in session or session["user_id"] != uid:
        return jsonify({"error": "Forbidden"}), 403

    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 10))
    skip = (page - 1) * limit

    cur = (
        db.diaries.find({"user_id": ObjectId(uid)})
        .sort("date", -1)
        .skip(skip)
        .limit(limit)
    )

    arr = []
    for d in cur:
        arr.append({
            "diary_id": str(d["_id"]),
            "date": d.get("date"),
            "title": d.get("title"),
            "preview": d.get("summary") or d.get("content", "")[:80],
            "mood": d.get("mood", "neutral"),
        })

    total = db.diaries.count_documents({"user_id": ObjectId(uid)})

    return jsonify({
        "diaries": arr,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit,
    })


@app.route("/api/diaries/<diary_id>", methods=["GET", "PUT", "DELETE"])
def diary_detail(diary_id):
    try:
        oid = ObjectId(diary_id)
    except:
        return jsonify({"error": "Invalid id"}), 400

    doc = db.diaries.find_one({"_id": oid})
    if not doc:
        return jsonify({"error": "Not found"}), 404

    # GET
    if request.method == "GET":
        return jsonify({
            "diary_id": str(doc["_id"]),
            "date": doc.get("date"),
            "time": doc.get("time"),            # ← 关键：这里要有 time
            "title": doc.get("title"),
            "content": doc.get("content", ""),
            "summary": doc.get("summary", ""),
            "mood": doc.get("mood", "neutral"),
            "mood_score": doc.get("mood_score", 0),
        })

    # PUT 更新内容
    if request.method == "PUT":
        data = request.get_json() or {}
        new_content = data.get("content")
        if new_content is not None:
            db.diaries.update_one(
                {"_id": oid},
                {"$set": {"content": new_content}}
            )
            doc["content"] = new_content

        return jsonify({
            "diary_id": str(doc["_id"]),
            "date": doc.get("date"),
            "time": doc.get("time"),
            "title": doc.get("title"),
            "content": doc.get("content", ""),
            "summary": doc.get("summary", ""),
            "mood": doc.get("mood", "neutral"),
            "mood_score": doc.get("mood_score", 0),
        })

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

    cur = db.diaries.find(
        {
            "user_id": ObjectId(uid),
            "$or": [
                {"title": {"$regex": q, "$options": "i"}},
                {"content": {"$regex": q, "$options": "i"}},
            ],
        }
    ).sort("date", -1).limit(30)

    arr = []
    for d in cur:
        arr.append({
            "diary_id": str(d["_id"]),
            "date": d.get("date"),
            "title": d.get("title"),
            "preview": d.get("summary") or d.get("content", "")[:80],
            "mood": d.get("mood", "neutral"),
        })

    return jsonify({"diaries": arr})


if __name__ == "__main__":
    app.run(debug=True)
