from types import SimpleNamespace
from datetime import datetime
from io import BytesIO
from bson import ObjectId

import app as webapp 


# --------- unit test: analyze_mood_and_summary ---------
def test_analyze_mood_and_summary_positive():
    texts = ["I am very happy today, it was an amazing trip!"]
    result = webapp.analyze_mood_and_summary(texts)

    assert result["mood"] == "positive"

    assert "trip" in result["title"].lower()

    assert result["summary"].startswith("I am very happy")


def test_analyze_mood_and_summary_negative():
    texts = ["I feel tired, stressed and very upset about the exam."]
    result = webapp.analyze_mood_and_summary(texts)

    assert result["mood"] == "negative"

    assert "exam" in result["title"].lower()

    assert result["summary"].startswith("I feel tired")


# --------- auth / basic pages ---------


def test_login_creates_new_user_and_redirects_home(client, fake_db):
    res_get = client.get("/login")
    assert res_get.status_code == 200

    res_post = client.post(
        "/login",
        data={"username": "alice", "password": "pw"},
        follow_redirects=False,
    )
    # should redirect to /home
    assert res_post.status_code == 302
    assert "/home" in res_post.headers["Location"]

    user = fake_db.users.find_one({"username": "alice"})
    assert user is not None
    assert user["password"] == "pw"


def test_home_requires_login(client):
    res = client.get("/home", follow_redirects=False)
    assert res.status_code == 302
    assert "/login" in res.headers["Location"]


# --------- conversations ---------


def test_start_conversation_requires_login(client):
    res = client.post("/api/conversations", json={})
    assert res.status_code == 401


def test_start_conversation_creates_conversation(client, fake_db, login_user):
    user_id = login_user() 

    res = client.post("/api/conversations", json={})
    assert res.status_code == 200
    data = res.get_json()
    assert "conversation_id" in data
    assert data["first_message"] 

    conv_oid = ObjectId(data["conversation_id"])
    conv = fake_db.conversations.find_one({"_id": conv_oid})
    assert conv is not None
    assert conv["user_id"] == user_id
    assert conv["status"] == "active"
    
    assert len(conv["messages"]) == 1
    assert conv["messages"][0]["role"] == "ai"


# --------- diaries list / detail / edit / delete / search ---------


def _insert_diary(fake_db, user_id, date="2025-01-01", time="10:00",
                  title="Test", content="hello world", mood="neutral"):
    return fake_db.diaries.insert_one(
        {
            "user_id": user_id,
            "date": date,
            "time": time,
            "title": title,
            "content": content,
            "summary": content[:20],
            "mood": mood,
            "mood_score": 0,
            "created_at": datetime.utcnow(),
            "conversation_id": ObjectId(),
        }
    ).inserted_id


def test_list_diaries_forbidden_for_other_user(client, fake_db, login_user):
    user1_id = login_user("user1", "pw1")

    user2_id = ObjectId()

    _insert_diary(fake_db, user2_id, title="User2 diary")

    res = client.get(f"/api/users/{user2_id}/diaries")
    assert res.status_code == 403


def test_diary_crud_and_search(client, fake_db, login_user):
    user_id = login_user("alice", "pw")

    d1_id = _insert_diary(
        fake_db,
        user_id,
        date="2025-01-02",
        time="09:00",
        title="Morning diary",
        content="Today I am happy.",
        mood="positive",
    )
    d2_id = _insert_diary(
        fake_db,
        user_id,
        date="2025-01-01",
        time="22:00",
        title="Night diary",
        content="I feel a bit tired.",
        mood="neutral",
    )

    # --- list_diaries ---
    res = client.get(f"/api/users/{user_id}/diaries?page=1&limit=10")
    assert res.status_code == 200
    data = res.get_json()
    assert data["total"] == 2
    assert data["diaries"][0]["title"] == "Morning diary"

    # --- diary_detail GET ---
    res = client.get(f"/api/diaries/{d1_id}")
    assert res.status_code == 200
    d = res.get_json()
    assert d["title"] == "Morning diary"
    assert d["content"] == "Today I am happy."

    # --- diary_detail PUT (edit) ---
    res = client.put(
        f"/api/diaries/{d1_id}",
        json={"content": "Updated content"},
    )
    assert res.status_code == 200
    d = res.get_json()
    assert d["content"] == "Updated content"

    stored = fake_db.diaries.find_one({"_id": d1_id})
    assert stored["content"] == "Updated content"

    # --- search_diaries ---
    res = client.get(f"/api/users/{user_id}/diaries/search?q=night")
    assert res.status_code == 200
    data = res.get_json()
    titles = [x["title"] for x in data["diaries"]]
    assert "Night diary" in titles

    # --- diary_detail DELETE ---
    res = client.delete(f"/api/diaries/{d2_id}")
    assert res.status_code == 200
    assert res.get_json()["deleted"] is True

    res = client.get(f"/api/diaries/{d2_id}")
    assert res.status_code == 404


# --------- complete_conversation fallback ---------


def test_complete_conversation_uses_fallback_when_ai_service_fails(
    client, fake_db, login_user, monkeypatch
):
    user_id = login_user("alice", "pw")

    conv_id = fake_db.conversations.insert_one(
        {
            "user_id": user_id,
            "created_at": datetime.utcnow(),
            "messages": [
                {"role": "ai", "text": "Hi! How was your day?"},
                {"role": "user", "text": "I am happy but a bit tired today."},
            ],
            "status": "active",
        }
    ).inserted_id

    def fake_post(*args, **kwargs):
        raise RuntimeError("ai-service down")

    monkeypatch.setattr(webapp, "requests", SimpleNamespace(post=fake_post))

    res = client.post(f"/api/conversations/{conv_id}/complete", json={})
    assert res.status_code == 200
    data = res.get_json()

    assert data["mood"] == "neutral"
    assert data["title"]  
    assert "day" in data["content"] or "happy" in data["content"]

    diaries_for_user = [
        d for d in fake_db.diaries.docs if d["user_id"] == user_id
    ]
    assert len(diaries_for_user) == 1
    assert diaries_for_user[0]["conversation_id"] == conv_id

    conv = fake_db.conversations.find_one({"_id": conv_id})
    assert conv["status"] == "completed"

def test_root_redirects_to_login(client):
    res = client.get("/", follow_redirects=False)
    assert res.status_code == 302
    assert "/login" in res.headers["Location"]


def test_logout_clears_session(client, login_user):
    login_user()
    res = client.get("/logout", follow_redirects=False)
    assert res.status_code == 302
    assert "/login" in res.headers["Location"]

    res2 = client.get("/home", follow_redirects=False)
    assert res2.status_code == 302
    assert "/login" in res2.headers["Location"]


def test_add_message_invalid_conversation_id(client, login_user):
    login_user()
    res = client.post(
        "/api/conversations/not-an-id/messages",
        json={"text": "hi"},
    )
    assert res.status_code == 400


def test_add_message_success(client, fake_db, login_user, monkeypatch):
    user_id = login_user()
    cid = fake_db.conversations.insert_one(
        {
            "user_id": user_id,
            "created_at": datetime.utcnow(),
            "messages": [],
            "status": "active",
        }
    ).inserted_id

    class FakeResp:
        def __init__(self):
            self.status_code = 200
            self.text = "ok"

        def json(self):
            return {"reply": "AI reply"}

    def fake_post(url, json=None, timeout=None):
        assert "/api/chat" in url
        assert json["user_id"] == str(user_id)
        assert json["text"] == "hi"
        return FakeResp()

    monkeypatch.setattr(webapp, "requests", SimpleNamespace(post=fake_post))

    res = client.post(
        f"/api/conversations/{cid}/messages",
        json={"text": "hi"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["user_message"] == "hi"
    assert data["ai_response"] == "AI reply"

    conv = fake_db.conversations.find_one({"_id": cid})
    assert len(conv["messages"]) == 2
    assert conv["messages"][0]["role"] == "user"
    assert conv["messages"][1]["role"] == "ai"


def test_add_audio_message_missing_file(client, fake_db, login_user):
    user_id = login_user()
    cid = fake_db.conversations.insert_one(
        {
            "user_id": user_id,
            "created_at": datetime.utcnow(),
            "messages": [],
            "status": "active",
        }
    ).inserted_id

    res = client.post(f"/api/conversations/{cid}/audio", data={})
    assert res.status_code == 400
    assert "No audio" in res.get_json()["error"]


def test_transcribe_missing_file(client, login_user):
    login_user()
    res = client.post("/api/transcribe", data={})
    assert res.status_code == 400
    assert "No audio" in res.get_json()["error"]


def test_transcribe_success(client, login_user, monkeypatch):
    login_user()

    class FakeResp:
        def __init__(self):
            self.status_code = 200
            self.text = "ok"

        def json(self):
            return {"text": "hello world"}

    def fake_post(url, files=None, timeout=None):
        assert "/api/transcribe" in url
        return FakeResp()

    monkeypatch.setattr(webapp, "requests", SimpleNamespace(post=fake_post))

    data = {"audio": (BytesIO(b"fake"), "voice.wav")}
    res = client.post(
        "/api/transcribe",
        data=data,
        content_type="multipart/form-data",
    )
    assert res.status_code == 200
    assert res.get_json()["text"] == "hello world"


def test_complete_conversation_uses_ai_diary(
    client, fake_db, login_user, monkeypatch
):
    user_id = login_user()

    cid = fake_db.conversations.insert_one(
        {
            "user_id": user_id,
            "created_at": datetime.utcnow(),
            "messages": [
                {"role": "ai", "text": "Hi"},
                {"role": "user", "text": "I am happy."},
            ],
            "status": "active",
        }
    ).inserted_id

    class FakeResp:
        def __init__(self):
            self.status_code = 200
            self.text = "ok"

        def json(self):
            return {
                "title": "AI diary title",
                "content": "AI diary content",
                "summary": "AI diary summary",
                "mood": "positive",
                "mood_score": 0.9,
            }

    def fake_post(url, json=None, timeout=None):
        assert "/api/generate-diary" in url
        assert "messages" in json
        return FakeResp()

    monkeypatch.setattr(webapp, "requests", SimpleNamespace(post=fake_post))

    res = client.post(
        f"/api/conversations/{cid}/complete",
        json={"preferences": {"tone": "casual"}},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["title"] == "AI diary title"
    assert data["mood"] == "positive"

    diary_id = ObjectId(data["diary_id"])
    diary = fake_db.diaries.find_one({"_id": diary_id})
    assert diary is not None
    assert diary["title"] == "AI diary title"

def test_add_audio_success_branch(client, fake_db, login_user, monkeypatch):
    user_id = login_user()

    cid = fake_db.conversations.insert_one(
        {
            "user_id": user_id,
            "created_at": datetime.utcnow(),
            "messages": [],
            "status": "active",
        }
    ).inserted_id

    class FakeResp:
        def __init__(self):
            self.status_code = 200
            self.text = "ok"

        def json(self):
            return {
                "reply": "Audio AI reply",
                "history": [
                    {"role": "ai", "text": "Hi"},
                    {"role": "user", "text": "Transcribed text"},
                ],
            }

    def fake_post(url, params=None, files=None, timeout=None):
        assert "/api/chat/audio" in url
        assert params["user_id"] == str(user_id)
        return FakeResp()

    monkeypatch.setattr(webapp, "requests", SimpleNamespace(post=fake_post))

    data = {"audio": (BytesIO(b"fake-audio"), "voice.wav")}
    res = client.post(
        f"/api/conversations/{cid}/audio",
        data=data,
        content_type="multipart/form-data",
    )

    assert res.status_code == 200
    js = res.get_json()
    assert js["user_message"] == "Transcribed text"
    assert js["ai_response"] == "Audio AI reply"

    conv = fake_db.conversations.find_one({"_id": cid})
    assert len(conv["messages"]) == 2
    assert conv["messages"][0]["role"] == "user"
    assert conv["messages"][1]["role"] == "ai"
