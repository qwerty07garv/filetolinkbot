import os
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://moviesbot:12345@cluster0.nhnd1.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0").strip().replace('"', '').replace("'", "")
DB_NAME = os.getenv("DB_NAME", "movieshouse_bot").strip().replace('"', '').replace("'", "")

db = None
local_file_db = {}
local_user_db = {}
is_async_mongo = False
mongo_client = None

def get_mongo():
    global mongo_client, db, is_async_mongo
    if mongo_client is None:
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
            mongo_client = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=1000)
            db = mongo_client[DB_NAME]
            is_async_mongo = True
        except Exception as e:
            logger.warning(f"⚠️ Motor Client Initialization failed ({e}). Operating in RAM fallback mode.")
            is_async_mongo = False
    return mongo_client, db

async def init_indexes():
    """Verify real MongoDB ping connection and initialize unique indexes lazily inside active loop."""
    global is_async_mongo, db
    m_client, m_db = get_mongo()
    if m_client is not None:
        try:
            await m_client.admin.command('ping')
            is_async_mongo = True
            logger.info("✅ Verified real MongoDB Connection via admin ping!")

            await m_db.files.create_index("file_id", unique=True)
            await m_db.users.create_index("user_id", unique=True)
            logger.info("⚡ MongoDB Indexes initialized: file_id (unique), user_id (unique)")
        except Exception as e:
            is_async_mongo = False
            logger.warning(f"⚠️ MongoDB connection test failed ({e}). Operating in temporary RAM fallback mode.")

async def mongo_health_check_loop():
    """Background task to continuously attempt MongoDB reconnection and sync RAM data."""
    global is_async_mongo
    while True:
        await asyncio.sleep(60)
        m_client, m_db = get_mongo()
        if m_client is not None:
            try:
                await m_client.admin.command('ping')
                if not is_async_mongo:
                    is_async_mongo = True
                    logger.info("🟢 MongoDB auto-reconnected successfully!")
                    if local_file_db:
                        for fid, rec in list(local_file_db.items()):
                            await m_db.files.update_one({"file_id": fid}, {"$set": rec}, upsert=True)
                        local_file_db.clear()
                    if local_user_db:
                        for uid, urec in list(local_user_db.items()):
                            await m_db.users.update_one({"user_id": uid}, {"$set": urec}, upsert=True)
                        local_user_db.clear()
                    logger.info("⚡ RAM fallback records synced to MongoDB!")
            except Exception:
                is_async_mongo = False

async def save_file_record(file_id, record):
    global is_async_mongo
    m_client, m_db = get_mongo()
    if is_async_mongo and m_db is not None:
        try:
            await m_db.files.update_one({"file_id": file_id}, {"$set": record}, upsert=True)
            return
        except Exception as e:
            logger.error(f"MongoDB save_file_record Error: {e}")
            is_async_mongo = False
    local_file_db[file_id] = record

async def get_file_record(file_id):
    global is_async_mongo
    m_client, m_db = get_mongo()
    if is_async_mongo and m_db is not None:
        try:
            record = await m_db.files.find_one({"file_id": file_id})
            if record:
                return record
        except Exception as e:
            logger.error(f"MongoDB get_file_record Error: {e}")
            is_async_mongo = False
    return local_file_db.get(file_id)

async def delete_file_record(file_id):
    global is_async_mongo
    local_file_db.pop(file_id, None)
    m_client, m_db = get_mongo()
    if is_async_mongo and m_db is not None:
        try:
            await m_db.files.delete_one({"file_id": file_id})
        except Exception as e:
            logger.error(f"MongoDB delete_file_record Error: {e}")
            is_async_mongo = False

async def save_user(user_id, first_name):
    global is_async_mongo
    user_data = {
        "user_id": user_id,
        "first_name": first_name,
        "updated_at": datetime.utcnow().isoformat()
    }
    m_client, m_db = get_mongo()
    if is_async_mongo and m_db is not None:
        try:
            await m_db.users.update_one({"user_id": user_id}, {"$set": user_data}, upsert=True)
            return
        except Exception as e:
            logger.error(f"MongoDB save_user Error: {e}")
            is_async_mongo = False
    local_user_db[user_id] = user_data

async def get_all_users():
    global is_async_mongo
    m_client, m_db = get_mongo()
    if is_async_mongo and m_db is not None:
        try:
            cursor = m_db.users.find({})
            users = await cursor.to_list(length=None)
            if users:
                return users
        except Exception as e:
            logger.error(f"MongoDB get_all_users Error: {e}")
            is_async_mongo = False
    return list(local_user_db.values())

async def get_total_stats():
    global is_async_mongo
    m_client, m_db = get_mongo()
    if is_async_mongo and m_db is not None:
        try:
            return await m_db.files.count_documents({})
        except Exception as e:
            logger.error(f"MongoDB get_total_stats Error: {e}")
            is_async_mongo = False
    return len(local_file_db)

async def get_total_users_count():
    global is_async_mongo
    m_client, m_db = get_mongo()
    if is_async_mongo and m_db is not None:
        try:
            return await m_db.users.count_documents({})
        except Exception as e:
            logger.error(f"MongoDB get_total_users_count Error: {e}")
            is_async_mongo = False
    return len(local_user_db)

async def acquire_global_bot_lock(instance_id):
    """Acquire a global distributed lock in MongoDB so ONLY 1 container/process runs MTProto client across all servers."""
    global is_async_mongo
    m_client, m_db = get_mongo()
    if is_async_mongo and m_db is not None:
        try:
            now = datetime.utcnow().timestamp()
            lock_doc = await m_db.bot_lock.find_one({"_id": "primary_bot_lock"})
            if lock_doc:
                last_heartbeat = lock_doc.get("heartbeat", 0)
                holder = lock_doc.get("holder", "")
                if holder != instance_id and (now - last_heartbeat < 20):
                    return False
            await m_db.bot_lock.update_one(
                {"_id": "primary_bot_lock"},
                {"$set": {"holder": instance_id, "heartbeat": now}},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"MongoDB acquire_global_bot_lock Error: {e}")
    return True
