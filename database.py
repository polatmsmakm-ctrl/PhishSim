import sqlite3
from pathlib import Path
from config import DB_PATH


def get_db_connection(db_path=None):
    path = Path(db_path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def init_db(db_path=None):
    with get_db_connection(db_path) as conn:
        conn.executescript("""
        PRAGMA journal_mode = WAL;
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'admin' CHECK(role IN ('admin','analyst')),
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS login_attempts (
            username TEXT PRIMARY KEY COLLATE NOCASE,
            failed_count INTEGER NOT NULL DEFAULT 0,
            locked_until TEXT,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            training_url TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('draft','active','paused','completed')),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            participant_ref TEXT NOT NULL,
            event_type TEXT NOT NULL CHECK(event_type IN ('click','report')),
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_events_campaign ON events(campaign_id);
        CREATE INDEX IF NOT EXISTS idx_events_participant ON events(campaign_id, participant_ref);
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            action TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);
        """)
    return str(Path(db_path or DB_PATH))


def log_audit(username, action, details="", db_path=None):
    with get_db_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO audit_log(username, action, details) VALUES (?, ?, ?)",
            (str(username)[:80], str(action)[:80], str(details)[:500])
        )


def backup_database(db_path=None, destination=None):
    """Create a consistent SQLite backup using SQLite's online backup API."""
    source = Path(db_path or DB_PATH)
    if not source.exists():
        raise FileNotFoundError("قاعدة البيانات غير موجودة.")
    target = Path(destination) if destination else source.with_name(
        f"{source.stem}_backup_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() == target.resolve():
        raise ValueError("مسار النسخة الاحتياطية يجب أن يختلف عن قاعدة البيانات.")
    with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    return str(target)
