import os
import sqlite3
import secrets
from werkzeug.security import generate_password_hash

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS classes(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, lang TEXT);
CREATE TABLE IF NOT EXISTS students(
    tg_id INTEGER PRIMARY KEY, username TEXT, tg_name TEXT, full_name TEXT,
    class_id INTEGER, lang TEXT, registered TEXT);
CREATE TABLE IF NOT EXISTS tests(
    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, lang TEXT,
    class_id INTEGER DEFAULT 0, seconds INTEGER DEFAULT 30, active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS questions(
    id INTEGER PRIMARY KEY AUTOINCREMENT, test_id INTEGER, text TEXT,
    a TEXT, b TEXT, c TEXT, d TEXT, correct INTEGER);
CREATE TABLE IF NOT EXISTS results(
    id INTEGER PRIMARY KEY AUTOINCREMENT, tg_id INTEGER, username TEXT, tg_name TEXT,
    full_name TEXT, class_name TEXT, lang TEXT, test_id INTEGER, test_title TEXT,
    score INTEGER DEFAULT 0, total INTEGER DEFAULT 0, percent REAL DEFAULT 0,
    started TEXT, finished TEXT, done INTEGER DEFAULT 0, answers TEXT);
CREATE TABLE IF NOT EXISTS messages(
    id INTEGER PRIMARY KEY AUTOINCREMENT, tg_id INTEGER, full_name TEXT, class_name TEXT,
    username TEXT, lang TEXT, text TEXT, created TEXT, reply TEXT, replied_at TEXT);
"""


def conn():
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    return c


def q(sql, args=(), one=False, commit=False):
    c = conn()
    try:
        cur = c.execute(sql, args)
        if commit:
            c.commit()
            return cur.lastrowid
        rows = cur.fetchall()
        if one:
            return rows[0] if rows else None
        return rows
    finally:
        c.close()


def get_setting(key, default=""):
    r = q("SELECT value FROM settings WHERE key=?", (key,), one=True)
    return r["value"] if r else default


def set_setting(key, value):
    q("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, value), commit=True)


def init():
    c = conn()
    c.executescript(SCHEMA)
    c.commit()
    c.close()
    defaults = {
        "student_password": "10maktab",       # o'quvchilar uchun umumiy parol
        "admin_login": "maktab10",
        "admin_hash": generate_password_hash("maktab10"),
        "show_result": "1",                   # natijani o'quvchiga ko'rsatish
        "shuffle": "1",                       # savol va variantlarni aralashtirish
        "secret": secrets.token_hex(24),
        "admin_ids": "",                      # Telegram admin ID lari (vergul bilan)
    }
    for k, v in defaults.items():
        q("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v), commit=True)
    # bir martalik: eski bazada ham yangi boshlang'ich login/parollar o'rnatiladi
    if not get_setting("defaults_v2"):
        set_setting("student_password", "10maktab")
        set_setting("admin_login", "maktab10")
        set_setting("admin_hash", generate_password_hash("maktab10"))
        set_setting("defaults_v2", "1")
