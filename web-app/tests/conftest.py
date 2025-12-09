import re
from types import SimpleNamespace

import pytest
from bson import ObjectId

import app as webapp 


class FakeCursor:
    def __init__(self, docs):
        self.docs = [d.copy() for d in docs]

    def sort(self, field, direction):
        reverse = direction == -1
        self.docs.sort(key=lambda d: d.get(field), reverse=reverse)
        return self

    def skip(self, n):
        self.docs = self.docs[n:]
        return self

    def limit(self, n):
        self.docs = self.docs[:n]
        return self

    def __iter__(self):
        return iter(self.docs)


class FakeCollection:
    def __init__(self):
        self.docs = []

    # ---- helpers ----
    def _match_simple(self, doc, key, value):
        # Handle comparison operators
        if isinstance(value, dict):
            doc_val = doc.get(key)
            
            # Handle regex
            if "$regex" in value:
                pattern = value["$regex"]
                flags = re.IGNORECASE if value.get("$options") == "i" else 0
                reg = re.compile(pattern, flags)
                return bool(reg.search(doc_val or ""))
            
            # Handle comparison operators
            if "$gte" in value:
                if doc_val is None:
                    return False
                if doc_val < value["$gte"]:
                    return False
            
            if "$gt" in value:
                if doc_val is None:
                    return False
                if doc_val <= value["$gt"]:
                    return False
            
            if "$lte" in value:
                if doc_val is None:
                    return False
                if doc_val > value["$lte"]:
                    return False
            
            if "$lt" in value:
                if doc_val is None:
                    return False
                if doc_val >= value["$lt"]:
                    return False
            
            if "$ne" in value:
                if doc_val == value["$ne"]:
                    return False
            
            # If we had operators and all passed
            if any(op in value for op in ["$gte", "$gt", "$lte", "$lt", "$ne"]):
                return True
        
        return doc.get(key) == value

    def _matches_filter(self, doc, flt):
        for key, value in flt.items():
            if key == "$or":
                if not any(self._matches_filter(doc, cond) for cond in value):
                    return False
            else:
                if not self._match_simple(doc, key, value):
                    return False
        return True

    # ---- Mongo-like API ----
    def insert_one(self, doc):
        if "_id" not in doc:
            doc["_id"] = ObjectId()
        self.docs.append(doc.copy())
        return SimpleNamespace(inserted_id=doc["_id"])

    def find_one(self, flt):
        for d in self.docs:
            if self._matches_filter(d, flt):
                return d.copy()
        return None

    def find(self, flt):
        matched = [d for d in self.docs if self._matches_filter(d, flt)]
        return FakeCursor(matched)

    def update_one(self, flt, update, upsert=False):
        for d in self.docs:
            if self._matches_filter(d, flt):
                if "$set" in update:
                    for k, v in update["$set"].items():
                        d[k] = v
                if "$push" in update:
                    for k, v in update["$push"].items():
                        if isinstance(v, dict) and "$each" in v:
                            d.setdefault(k, [])
                            d[k].extend(v["$each"])
                        else:
                            d.setdefault(k, [])
                            d[k].append(v)
                return

    def delete_one(self, flt):
        for i, d in enumerate(self.docs):
            if self._matches_filter(d, flt):
                del self.docs[i]
                return

    def count_documents(self, flt):
        return sum(1 for d in self.docs if self._matches_filter(d, flt))


class FakeDB:

    def __init__(self):
        self.users = FakeCollection()
        self.conversations = FakeCollection()
        self.diaries = FakeCollection()


@pytest.fixture
def fake_db(monkeypatch):
    
    db = FakeDB()
  
    monkeypatch.setattr(webapp, "db", db)
    return db


@pytest.fixture
def app(fake_db): 
    webapp.app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
    )
    return webapp.app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def login_user(client, fake_db):
    """
    return helper: login(username, password) -> user_id(ObjectId)

    """

    def _login(username="alice", password="pw"):
        res = client.post(
            "/login",
            data={"username": username, "password": password},
            follow_redirects=False,
        )
        assert res.status_code == 302 
        user = fake_db.users.find_one({"username": username})
        assert user is not None
        return user["_id"]

    return _login
