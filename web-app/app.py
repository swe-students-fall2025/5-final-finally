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

client = MongoClient("mongodb://localhost:27017/")
db = client["diary_db"]

app = Flask(__name__)
app.secret_key = "dev-secret-key" 


@app.route("/")
def root():
    return redirect(url_for("login"))


#login
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":

        if "user_id" in session:
            return redirect(url_for("home"))
        return render_template("login.html")

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    if not username or not password:
        return render_template(
            "login.html",
            error="Username and password are required.",
            username=username,
        )

    users_col = db.users
    user = users_col.find_one({"username": username})

    if user:
        if user.get("password") != password:
            return render_template(
                "login.html",
                error="Wrong password for this username.",
                username=username,
            )
    else:
        new_id = users_col.insert_one(
            {"username": username, "password": password}
        ).inserted_id
        user = users_col.find_one({"_id": new_id})

    # save session
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
        "index.html",
        user_id=session["user_id"],
        username=session["username"],
    )


# =====================================================
# Conversation APIs (stub ver.)
# =====================================================

# 1) new conversation
@app.route("/api/conversations", methods=["POST"])
def start_conversation():
    data = request.get_json() or {}
    user_id = data.get("user_id")

    if not user_id:
        return jsonify({"error": "user_id required"}), 400

    conv_doc = {
        "user_id": ObjectId(user_id),
        "created_at": datetime.utcnow(),
        "messages": [],
        "status": "active",
    }
    result = db.conversations.insert_one(conv_doc)
    conv_id = str(result.inserted_id)

    first_message = "Hi! How was your day?"

    db.conversations.update_one(
        {"_id": result.inserted_id},
        {
            "$push": {
                "messages": {"role": "ai", "text": first_message}
            }
        },
    )

    return jsonify(
        {
            "conversation_id": conv_id,
            "first_message": first_message,
        }
    )


# 2) receive messages
@app.route("/api/conversations/<conv_id>/messages", methods=["POST"])
def add_message(conv_id):
    try:
        conv_obj_id = ObjectId(conv_id)
    except Exception:
        return jsonify({"error": "Invalid conversation id"}), 400

    conv = db.conversations.find_one({"_id": conv_obj_id})
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404

    # 这里正常会读 audio 文件并调 AI Service，我们先写 stub：
    user_message = "This is a placeholder transcription of your audio."
    ai_response = "Thanks for sharing! Tell me more about your day."

    # 把对话追加到 MongoDB（可选，之后 AI 模块可以复用）
    db.conversations.update_one(
        {"_id": conv_obj_id},
        {
            "$push": {
                "messages": {
                    "$each": [
                        {"role": "user", "text": user_message},
                        {"role": "ai", "text": ai_response},
                    ]
                }
            }
        },
    )

    return jsonify(
        {
            "user_message": user_message,
            "ai_response": ai_response,
        }
    )


# 3) generate diary
@app.route("/api/conversations/<conv_id>/complete", methods=["POST"])
def complete_conversation(conv_id):
    try:
        conv_obj_id = ObjectId(conv_id)
    except Exception:
        return jsonify({"error": "Invalid conversation id"}), 400

    conv = db.conversations.find_one({"_id": conv_obj_id})
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404

    user_id = conv["user_id"]
    now = datetime.utcnow()
    date_str = now.strftime("%Y-%m-%d")

    # diary placement section (fake)
    msgs = conv.get("messages", [])
    user_texts = [m["text"] for m in msgs if m.get("role") == "user"]
    diary_content = (
        "Today you talked about: " + " ".join(user_texts)
        if user_texts
        else "Today you had a short chat with your AI diary."
    )

    diary_title = f"Diary for {date_str}"

    diary_doc = {
        "user_id": user_id,
        "date": date_str,
        "title": diary_title,
        "content": diary_content,
        "created_at": now,
        "conversation_id": conv_obj_id,
    }

    result = db.diaries.insert_one(diary_doc)

    # complete conversation
    db.conversations.update_one(
        {"_id": conv_obj_id}, {"$set": {"status": "completed"}}
    )

    return jsonify(
        {
            "diary_id": str(result.inserted_id),
            "date": date_str,
            "title": diary_title,
            "content": diary_content,
        }
    )


# diary list
@app.route("/api/users/<user_id>/diaries")
def get_user_diaries(user_id):
    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 10))
    skip = (page - 1) * limit

    diaries_col = db.diaries

    total = diaries_col.count_documents({"user_id": ObjectId(user_id)})
    cursor = (
        diaries_col.find({"user_id": ObjectId(user_id)})
        .sort("date", -1)
        .skip(skip)
        .limit(limit)
    )

    diaries = []
    for d in cursor:
        diaries.append(
            {
                "diary_id": str(d["_id"]),
                "date": d.get("date"),
                "title": d.get("title"),
                "preview": d.get("content", "")[:80],
            }
        )

    return jsonify(
        {
            "diaries": diaries,
            "total": total,
            "page": page,
            "pages": (total + limit - 1) // limit,
        }
    )

#details
@app.route("/api/diaries/<diary_id>")
def get_diary_detail(diary_id):
    diaries_col = db.diaries
    try:
        obj_id = ObjectId(diary_id)
    except Exception:
        return jsonify({"error": "Invalid diary id"}), 400

    doc = diaries_col.find_one({"_id": obj_id})
    if not doc:
        return jsonify({"error": "Not found"}), 404

    return jsonify(
        {
            "diary_id": str(doc["_id"]),
            "date": doc.get("date"),
            "title": doc.get("title"),
            "content": doc.get("content", ""),
        }
    )

if __name__ == "__main__":
    app.run(debug=True)
