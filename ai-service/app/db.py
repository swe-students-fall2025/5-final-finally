from datetime import datetime, timezone
from pymongo import MongoClient
from typing import Dict, Any
import os

# ----------------------------------------
# MongoDB Connection 
# ----------------------------------------
# Priority:
#   1. Use MONGO_URI from environment (Docker)
#   2. Fallback to localhost for local development
# ----------------------------------------

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = "ai_diary"

print(">>> Using MongoDB URI:", MONGO_URI)

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

# conversations collection
conversations = db["conversations"]


# ----------------------------------------
# Create or get today's active conversation
# ----------------------------------------
def create_or_get_conversation(user_id: str) -> Dict[str, Any]:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    conv = conversations.find_one({
        "user_id": user_id,
        "date": today,
        "status": "active",
    })

    if conv:
        return conv

    new_conv = {
        "user_id": user_id,
        "date": today,
        "messages": [],
        "status": "active",
        "created_at": datetime.now(timezone.utc),
    }

    result = conversations.insert_one(new_conv)
    new_conv["_id"] = result.inserted_id
    return new_conv



# ----------------------------------------
# Append message to conversation
# ----------------------------------------
def append_message(conv_id, role: str, text: str):
    message = {
        "role": role,
        "text": text,
        "timestamp": datetime.now(timezone.utc),
    }

    conversations.update_one(
        {"_id": conv_id},
        {"$push": {"messages": message}},
    )
