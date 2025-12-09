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


def test_login_missing_fields(client):
    """Test login with missing fields (both username and password empty, or just username)"""
    # Test with both fields empty
    res = client.post("/login", data={"username": "", "password": ""})
    assert res.status_code == 200
    assert "Missing fields" in res.get_data(as_text=True)
    
    # Test with only username missing
    res = client.post("/login", data={"username": ""})
    assert res.status_code == 200
    assert "Missing fields" in res.get_data(as_text=True)


def test_home_requires_login(client):
    res = client.get("/home", follow_redirects=False)
    assert res.status_code == 302
    assert "/login" in res.headers["Location"]


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


def test_add_message_forbidden_for_other_user(client, fake_db, login_user):
    user1 = login_user("user1", "pw")   # logged in user

    # conversation belongs to user2
    user2 = ObjectId()
    cid = fake_db.conversations.insert_one(
        {
            "user_id": user2,
            "created_at": datetime.utcnow(),
            "messages": [],
            "status": "active",
        }
    ).inserted_id

    res = client.post(
        f"/api/conversations/{cid}/messages",
        json={"text": "hi"},
    )
    assert res.status_code == 403
    assert res.get_json()["error"] == "Forbidden"


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


def test_complete_conversation_invalid_id(client, login_user):
    login_user()
    res = client.post("/api/conversations/not-an-id/complete", json={})
    assert res.status_code == 400
    assert res.get_json()["error"] == "Invalid id"


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

    # Now complete returns preview only, not saved yet
    assert data["mood"] == "neutral"
    assert data["title"]
    assert data["conversation_id"] == str(conv_id)
    assert "suggested_date" in data


def test_complete_conversation_uses_ai_diary(client, fake_db, login_user, monkeypatch):
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

    # Step 1: Complete returns preview only
    res = client.post(
        f"/api/conversations/{cid}/complete",
        json={"preferences": {"tone": "casual"}},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["title"] == "AI diary title"
    assert data["mood"] == "positive"
    assert data["conversation_id"] == str(cid)

    # Step 2: Save the diary
    res2 = client.post(
        f"/api/conversations/{cid}/save",
        json={
            "title": data["title"],
            "content": data["content"],
            "mood": data["mood"],
            "mood_score": data["mood_score"],
            "entry_date": data["suggested_date"],
        },
    )
    assert res2.status_code == 200
    save_data = res2.get_json()
    assert "diary_id" in save_data

    diary_id = ObjectId(save_data["diary_id"])
    diary = fake_db.diaries.find_one({"_id": diary_id})
    assert diary is not None
    assert diary["title"] == "AI diary title"


def test_save_diary_invalid_entry_date(client, fake_db, login_user):
    """Test saving diary with invalid entry_date - should fallback to today's date"""
    user_id = login_user()

    cid = fake_db.conversations.insert_one(
        {
            "user_id": user_id,
            "created_at": datetime.utcnow(),
            "messages": [],
            "status": "active",
        }
    ).inserted_id

    # First complete to ensure preview
    client.post(f"/api/conversations/{cid}/complete", json={})

    # Try to save with invalid date
    res = client.post(
        f"/api/conversations/{cid}/save",
        json={
            "title": "Test",
            "content": "Content",
            "mood": "neutral",
            "mood_score": 0,
            "entry_date": "invalid-date",
        },
    )
    assert res.status_code == 200
    
    js = res.get_json()
    # entry_date should fallback to today's date (YYYY-MM-DD format)
    assert len(js["entry_date"]) == 10
    assert js["entry_date"].count("-") == 2
    assert js["entry_date"][4] == "-"


# --------- transcribe ---------


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


# --------- diaries list / detail / edit / delete / search ---------


def _insert_diary(
    fake_db,
    user_id,
    date="2025-01-01",
    time="10:00",
    title="Test",
    content="hello world",
    mood="neutral",
):
    return fake_db.diaries.insert_one(
        {
            "user_id": user_id,
            "entry_date": date,
            "created_date": date,
            "created_time": time,
            "date": date,  # Keep for backward compatibility
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


def test_diary_detail_invalid_id(client):
    res = client.get("/api/diaries/not-a-valid-id")
    assert res.status_code == 400
    assert res.get_json()["error"] == "Invalid id"


def test_search_empty_query(client, login_user):
    uid = login_user()
    res = client.get(f"/api/users/{uid}/diaries/search?q=")
    assert res.status_code == 200
    assert res.get_json() == {"diaries": []}


# --------- calendar view tests ---------


def test_get_calendar_diaries_forbidden(client, fake_db, login_user):
    """Test calendar access forbidden for other users"""
    user1 = login_user("user1", "pw")
    user2 = ObjectId()
    
    res = client.get(f"/api/users/{user2}/diaries/calendar")
    assert res.status_code == 403


def test_get_calendar_diaries_success(client, fake_db, login_user):
    """Test calendar view returns diaries grouped by date"""
    user_id = login_user("alice", "pw")
    
    # Convert user_id string to ObjectId for database insertion
    user_oid = ObjectId(user_id)
    
    # Insert diaries for January 2025 directly to ensure correct field names
    fake_db.diaries.insert_one({
        "user_id": user_oid,
        "entry_date": "2025-01-15",
        "created_date": "2025-01-15",
        "created_time": "10:00",
        "date": "2025-01-15",
        "time": "10:00",
        "title": "Mid Jan diary",
        "content": "Test content",
        "summary": "Test content",
        "mood": "positive",
        "mood_score": 0,
        "created_at": datetime.utcnow(),
        "conversation_id": ObjectId(),
    })
    fake_db.diaries.insert_one({
        "user_id": user_oid,
        "entry_date": "2025-01-15",
        "created_date": "2025-01-15",
        "created_time": "20:00",
        "date": "2025-01-15",
        "time": "20:00",
        "title": "Another Jan 15 diary",
        "content": "More content",
        "summary": "More content",
        "mood": "neutral",
        "mood_score": 0,
        "created_at": datetime.utcnow(),
        "conversation_id": ObjectId(),
    })
    fake_db.diaries.insert_one({
        "user_id": user_oid,
        "entry_date": "2025-01-20",
        "created_date": "2025-01-20",
        "created_time": "12:00",
        "date": "2025-01-20",
        "time": "12:00",
        "title": "Late Jan diary",
        "content": "Final content",
        "summary": "Final content",
        "mood": "negative",
        "mood_score": 0,
        "created_at": datetime.utcnow(),
        "conversation_id": ObjectId(),
    })
    
    # Query January 2025
    res = client.get(f"/api/users/{user_id}/diaries/calendar?year=2025&month=1")
    assert res.status_code == 200
    
    data = res.get_json()
    assert data["year"] == 2025
    assert data["month"] == 1
    assert "diaries_by_date" in data
    
    # Check grouped diaries
    diaries_by_date = data["diaries_by_date"]
    assert "2025-01-15" in diaries_by_date
    assert len(diaries_by_date["2025-01-15"]) == 2
    assert "2025-01-20" in diaries_by_date
    assert len(diaries_by_date["2025-01-20"]) == 1


def test_get_calendar_diaries_default_current_month(client, fake_db, login_user):
    """Test calendar defaults to current month if no params provided"""
    user_id = login_user()
    
    res = client.get(f"/api/users/{user_id}/diaries/calendar")
    assert res.status_code == 200
    
    data = res.get_json()
    assert "year" in data
    assert "month" in data
    assert "diaries_by_date" in data
