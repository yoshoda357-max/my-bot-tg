import time
import secrets
import aiosqlite
import os

# Постоянная папка для Bothost
DATA_DIR = "/app/data" if os.path.exists("/app/data") else "."
DB_PATH = os.path.join(DATA_DIR, "postman.db")

async def db_init() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS tickets(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            target_type TEXT NOT NULL,
            target TEXT NOT NULL,
            letter_type TEXT NOT NULL,
            created_at REAL NOT NULL)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS last_run(
            user_id INTEGER PRIMARY KEY, ts REAL NOT NULL)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS access(
            user_id INTEGER PRIMARY KEY,
            paid_at REAL NOT NULL,
            charge_id TEXT NOT NULL,
            stars INTEGER NOT NULL)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS donations(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            charge_id TEXT NOT NULL,
            created_at REAL NOT NULL)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            joined_at REAL NOT NULL)""")
        await db.commit()

async def db_add_user(uid: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users(user_id, joined_at) VALUES(?,?)",
            (uid, time.time()))
        await db.commit()

async def db_get_all_users() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id FROM users")
        rows = await cur.fetchall()
    return [r[0] for r in rows]

async def db_cooldown(uid: int, sec: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT ts FROM last_run WHERE user_id=?", (uid,))
        row = await cur.fetchone()
    return max(0, int(sec - (time.time() - row[0]))) if row else 0

async def db_mark_run(uid: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO last_run(user_id,ts) VALUES(?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET ts=excluded.ts",
            (uid, time.time()))
        await db.commit()

async def db_ticket(uid, tt, target, lt) -> str:
    tk = secrets.token_hex(4).upper()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO tickets(ticket,user_id,target_type,target,letter_type,created_at)"
            " VALUES(?,?,?,?,?,?)", (tk, uid, tt, target, lt, time.time()))
        await db.commit()
    return tk

async def db_has_access(uid: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT 1 FROM access WHERE user_id=?", (uid,))
        return (await cur.fetchone()) is not None

async def db_grant_access(uid: int, charge_id: str, stars: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO access(user_id,paid_at,charge_id,stars)"
            " VALUES(?,?,?,?)", (uid, time.time(), charge_id, stars))
        await db.commit()

async def db_save_donation(uid: int, amount: int, charge_id: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO donations(user_id,amount,charge_id,created_at)"
            " VALUES(?,?,?,?)", (uid, amount, charge_id, time.time()))
        await db.commit()