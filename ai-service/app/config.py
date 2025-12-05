import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017/")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
