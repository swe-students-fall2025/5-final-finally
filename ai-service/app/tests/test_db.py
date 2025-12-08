from unittest.mock import MagicMock, patch
from app import db
from datetime import datetime, timezone

def test_create_or_get_conversation_new():
    fake_collection = MagicMock()
    fake_collection.find_one.return_value = None
    fake_collection.insert_one.return_value.inserted_id = "fakeid"

    with patch.object(db, "conversations", fake_collection):
        conv = db.create_or_get_conversation("user123")

    assert conv["user_id"] == "user123"
    assert conv["_id"] == "fakeid"
    assert conv["status"] == "active"

def test_create_or_get_conversation_existing():
    fake_conv = {"_id": "abc", "user_id": "u1"}
    fake_collection = MagicMock()
    fake_collection.find_one.return_value = fake_conv

    with patch.object(db, "conversations", fake_collection):
        conv = db.create_or_get_conversation("u1")

    assert conv == fake_conv

def test_append_message():
    fake_collection = MagicMock()

    with patch.object(db, "conversations", fake_collection):
        db.append_message("abc123", "user", "hello test")

    fake_collection.update_one.assert_called_once()
