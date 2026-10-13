import sqlite3
import os
import time
from typing import List, Dict, Any, Optional

DB_PATH = "/storage/emulated/0/TelegramBotHost/database/users.db"

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # ১. Users Table (ডিফল্ট ফ্রি লিমিট বাধ্যতামূলক ১টি বট)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            status TEXT DEFAULT 'active',
            bot_limit INTEGER DEFAULT 1,
            created_at REAL,
            last_activity REAL
        );
        """)
        
        # ২. Hosted Bots Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS hosted_projects (
            bot_id TEXT PRIMARY KEY,
            user_id INTEGER,
            project_name TEXT,
            project_dir TEXT,
            main_file TEXT,
            status TEXT DEFAULT 'STOPPED',
            pid INTEGER DEFAULT 0,
            uptime_start REAL DEFAULT 0,
            restart_count INTEGER DEFAULT 0,
            last_exit_code INTEGER DEFAULT 0,
            last_error TEXT DEFAULT '',
            created_at REAL,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        );
        """)
        
        # ৩. Payment Requests Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS payment_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            plan_name TEXT,
            extra_bots INTEGER,
            amount TEXT,
            method TEXT,
            trx_id TEXT,
            status TEXT DEFAULT 'PENDING',
            created_at REAL
        );
        """)

        # ৪. Dynamic Required Channels Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS channel_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT UNIQUE,
            display_name TEXT,
            invite_url TEXT,
            is_enabled INTEGER DEFAULT 1,
            created_at REAL
        );
        """)
        
        # ৫. Dynamic Settings Table (নম্বর ও প্ল্যান কনফিগ)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS hosting_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """)

        # ডিফল্ট সেটিংস ইনস্টল
        default_settings = {
            "channel_protection": "1",
            "maintenance_mode": "0",
            "pay_bkash": "017XXXXXXXX (Personal bKash)",
            "pay_nagad": "018XXXXXXXX (Personal Nagad)",
            "pay_rocket": "019XXXXXXXX (Personal Rocket)",
            "pay_crypto": "USDT (TRC20): Txxxxxxxxxxxxxxxxxxxxxxxxx",
            "plan_starter_price": "50 BDT",
            "plan_starter_bots": "2",
            "plan_pro_price": "100 BDT",
            "plan_pro_bots": "5",
            "plan_ultra_price": "200 BDT",
            "plan_ultra_bots": "12"
        }

        for k, v in default_settings.items():
            cursor.execute("INSERT OR IGNORE INTO hosting_settings (key, value) VALUES (?, ?);", (k, v))

        conn.commit()

# --- User Management ---

def register_user(user_id: int, username: str, first_name: str, default_limit: int = 1):
    now = time.time()
    with get_db_connection() as conn:
        conn.execute("""
        INSERT INTO users (user_id, username, first_name, status, bot_limit, created_at, last_activity)
        VALUES (?, ?, ?, 'active', ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username=excluded.username,
            first_name=excluded.first_name,
            last_activity=excluded.last_activity;
        """, (user_id, username or "", first_name or "", default_limit, now, now))
        conn.commit()

def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

def add_user_limit(user_id: int, extra: int):
    with get_db_connection() as conn:
        conn.execute("UPDATE users SET bot_limit = bot_limit + ? WHERE user_id = ?", (extra, user_id))
        conn.commit()

def get_all_users() -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        rows = conn.execute("SELECT * FROM users").fetchall()
        return [dict(r) for r in rows]

# --- Channel Guard Queries ---

def get_channels(enabled_only: bool = False) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        query = "SELECT * FROM channel_settings"
        if enabled_only:
            query += " WHERE is_enabled = 1"
        rows = conn.execute(query).fetchall()
        return [dict(r) for r in rows]

def add_channel(channel_id: str, display_name: str, invite_url: str):
    with get_db_connection() as conn:
        conn.execute("""
        INSERT INTO channel_settings (channel_id, display_name, invite_url, is_enabled, created_at)
        VALUES (?, ?, ?, 1, ?)
        ON CONFLICT(channel_id) DO UPDATE SET
            display_name=excluded.display_name,
            invite_url=excluded.invite_url,
            is_enabled=1
        """, (channel_id, display_name, invite_url, time.time()))
        conn.commit()

def remove_channel(channel_id: str):
    with get_db_connection() as conn:
        conn.execute("DELETE FROM channel_settings WHERE channel_id = ?", (channel_id,))
        conn.commit()

# --- Dynamic Settings (bKash/Nagad/Plans) ---

def get_setting(key: str, default: str = "") -> str:
    with get_db_connection() as conn:
        row = conn.execute("SELECT value FROM hosting_settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

def set_setting(key: str, value: str):
    with get_db_connection() as conn:
        conn.execute("""
        INSERT INTO hosting_settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """, (key, value))
        conn.commit()

# --- Payments Queries ---

def create_payment_request(user_id: int, plan_name: str, extra_bots: int, amount: str, method: str, trx_id: str) -> int:
    with get_db_connection() as conn:
        cur = conn.execute("""
        INSERT INTO payment_requests (user_id, plan_name, extra_bots, amount, method, trx_id, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?)
        """, (user_id, plan_name, extra_bots, amount, method, trx_id, time.time()))
        conn.commit()
        return cur.lastrowid

def get_payment_request(request_id: int) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM payment_requests WHERE id = ?", (request_id,)).fetchone()
        return dict(row) if row else None

def update_payment_status(request_id: int, status: str):
    with get_db_connection() as conn:
        conn.execute("UPDATE payment_requests SET status = ? WHERE id = ?", (status, request_id))
        conn.commit()

# --- Projects Queries ---

def add_project(bot_id: str, user_id: int, project_name: str, project_dir: str, main_file: str):
    with get_db_connection() as conn:
        conn.execute("""
        INSERT INTO hosted_projects (bot_id, user_id, project_name, project_dir, main_file, status, created_at)
        VALUES (?, ?, ?, ?, ?, 'STOPPED', ?)
        """, (bot_id, user_id, project_name, project_dir, main_file, time.time()))
        conn.commit()

def get_project(bot_id: str) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM hosted_projects WHERE bot_id = ?", (bot_id,)).fetchone()
        return dict(row) if row else None

def get_user_projects(user_id: int) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        rows = conn.execute("SELECT * FROM hosted_projects WHERE user_id = ?", (user_id,)).fetchall()
        return [dict(r) for r in rows]

def get_all_projects() -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        rows = conn.execute("SELECT * FROM hosted_projects").fetchall()
        return [dict(r) for r in rows]

def update_project_status(bot_id: str, status: str, pid: int = 0, uptime_start: float = 0,
                          exit_code: int = 0, last_error: str = "", restart_count: int = None):
    with get_db_connection() as conn:
        if restart_count is not None:
            conn.execute("""
            UPDATE hosted_projects
            SET status=?, pid=?, uptime_start=?, last_exit_code=?, last_error=?, restart_count=?
            WHERE bot_id=?
            """, (status, pid, uptime_start, exit_code, last_error, restart_count, bot_id))
        else:
            conn.execute("""
            UPDATE hosted_projects
            SET status=?, pid=?, uptime_start=?, last_exit_code=?, last_error=?
            WHERE bot_id=?
            """, (status, pid, uptime_start, exit_code, last_error, bot_id))
        conn.commit()

def delete_project_record(bot_id: str):
    with get_db_connection() as conn:
        conn.execute("DELETE FROM hosted_projects WHERE bot_id = ?", (bot_id,))
        conn.commit()