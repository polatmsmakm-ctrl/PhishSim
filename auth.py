import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from database import get_db_connection, log_audit

_ITERATIONS = 310_000
_MAX_FAILURES = 5
_LOCK_MINUTES = 15
# Used to make unknown-user attempts perform a password hash too.
_DUMMY_HASH = ""  # initialized lazily per process


def _hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"{salt.hex()}${digest.hex()}"


def _verify_password(password, encoded):
    try:
        salt_hex, digest_hex = encoded.split("$", 1)
        candidate = _hash_password(password, bytes.fromhex(salt_hex)).split("$", 1)[1]
        return hmac.compare_digest(candidate, digest_hex)
    except (ValueError, TypeError, AttributeError):
        return False


class AuthManager:
    def __init__(self, db_path=None):
        self.db_path = db_path
        self.username = None
        global _DUMMY_HASH
        if not _DUMMY_HASH:
            _DUMMY_HASH = _hash_password("constant-time-dummy-password")

    def has_users(self):
        with get_db_connection(self.db_path) as conn:
            return conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None

    def create_admin(self, username, password):
        username = str(username or "").strip()
        if len(username) < 3 or len(username) > 80:
            raise ValueError("اسم المستخدم يجب أن يكون بين 3 و80 حرفاً.")
        if len(password) < 12:
            raise ValueError("كلمة المرور يجب ألا تقل عن 12 حرفاً.")
        if password.strip() != password:
            raise ValueError("لا تبدأ كلمة المرور بمسافة ولا تنتهِ بها.")
        with get_db_connection(self.db_path) as conn:
            if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                raise RuntimeError("تم إعداد حساب المشرف مسبقاً.")
            conn.execute(
                "INSERT INTO users(username, password_hash, role) VALUES (?, ?, 'admin')",
                (username, _hash_password(password))
            )
        log_audit(username, "admin_created", "إنشاء حساب المشرف", self.db_path)

    def login(self, username, password):
        username = str(username or "").strip()
        now = datetime.now(timezone.utc)
        with get_db_connection(self.db_path) as conn:
            attempt = conn.execute(
                "SELECT failed_count, locked_until FROM login_attempts WHERE username=?", (username,)
            ).fetchone()
            if attempt and attempt["locked_until"]:
                try:
                    if datetime.fromisoformat(attempt["locked_until"]) > now:
                        _verify_password(password, _DUMMY_HASH)
                        return False
                except ValueError:
                    pass
            row = conn.execute(
                "SELECT username, password_hash FROM users WHERE username = ?", (username,)
            ).fetchone()
            valid = _verify_password(password, row["password_hash"] if row else _DUMMY_HASH)
            if row and valid:
                conn.execute("DELETE FROM login_attempts WHERE username=?", (username,))
                self.username = row["username"]
            else:
                count = (attempt["failed_count"] if attempt else 0) + 1
                locked_until = (now + timedelta(minutes=_LOCK_MINUTES)).isoformat() if count >= _MAX_FAILURES else None
                conn.execute("""INSERT INTO login_attempts(username, failed_count, locked_until, updated_at)
                    VALUES (?, ?, ?, ?) ON CONFLICT(username) DO UPDATE SET
                    failed_count=excluded.failed_count, locked_until=excluded.locked_until,
                    updated_at=excluded.updated_at""",
                    (username[:80], count, locked_until, now.isoformat()))
                return False
        log_audit(self.username, "login", "تسجيل دخول ناجح", self.db_path)
        return True

    def logout(self):
        if self.username:
            log_audit(self.username, "logout", "تسجيل خروج", self.db_path)
        self.username = None

    def is_authenticated(self):
        return self.username is not None
