from datetime import datetime, timezone
from pymongo import MongoClient
from typing import Dict, Any


# ----------------------------------------
# MongoDB Connection (local development)
# ----------------------------------------
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "ai_diary"

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

# conversations collection
conversations = db["conversations"]


# ----------------------------------------
# Create or get today's active conversation
# ----------------------------------------
def create_or_get_conversation(user_id: str) -> Dict[str, Any]:
    """
    Retrieves the user's active conversation for today, or creates a new one if none exists.
    Uses YYYY-MM-DD as the date identifier, which is well-suited for a "one diary entry per day" structure.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Look for an active conversation for the user today
    conv = conversations.find_one({
        "user_id": user_id,
        "date": today,
        "status": "active",
    })

    if conv:
        return conv

    # Create a new conversation if none is found
    new_conv = {
        "user_id": user_id,
        "date": today,
        "messages": [],
        "status": "active",
        "created_at": datetime.now(timezone.utc),
    }

    result = conversations.insert_one(new_conv)
    # Ensure the _id is available in the returned object
    new_conv["_id"] = result.inserted_id
    return new_conv


# ----------------------------------------
# Append a message to a conversation
# ----------------------------------------
def append_message(conv_id, role: str, text: str):
    """
    Appends a message to a specific conversation.
    role: "user" or "ai"
    """
    message = {
        "role": role,
        "text": text,
        "timestamp": datetime.now(timezone.utc),
    }

    conversations.update_one(
        {"_id": conv_id},
        {"$push": {"messages": message}},
    )