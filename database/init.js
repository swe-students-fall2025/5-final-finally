db = db.getSiblingDB('ai_diary');

// create conversations collection
db.createCollection('conversations');

// user_id + date 
db.conversations.createIndex({ user_id: 1, date: 1 });

// status index
db.conversations.createIndex({ status: 1 });
