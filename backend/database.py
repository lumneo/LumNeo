# backend/database.py
import os
import aiosqlite
from config_loader import config


async def get_db():
    db = await aiosqlite.connect(f"{config.data_dir}/data/lumneo.db")
    db.row_factory = aiosqlite.Row
    return db

async def init_db():
    os.makedirs(os.path.dirname(f"{config.data_dir}/data/lumneo.db"), exist_ok=True)
    db = await get_db()

    await db.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id TEXT PRIMARY KEY,
            title TEXT DEFAULT '新对话',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            file_ref TEXT DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            tools TEXT NOT NULL DEFAULT '[]',
            profile_prompt TEXT DEFAULT '',
            temperature REAL DEFAULT 1.0,
            top_p REAL DEFAULT 1.0,
            top_k INTEGER DEFAULT 40,
            frequency_penalty REAL DEFAULT 0.0,
            presence_penalty REAL DEFAULT 0.0
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS models (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            modelName TEXT NOT NULL,
            baseUrl TEXT NOT NULL,
            apiKey TEXT NOT NULL
        )
    """)

    await db.commit()
    await db.close()