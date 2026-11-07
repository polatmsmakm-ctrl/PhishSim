"""Local-network API for the authorized PhishSim awareness-training manager.

This API deliberately does not send email, host imitation login pages, or collect credentials.
Run only on a trusted private LAN; do not expose port 8765 to the internet.
"""
import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from auth import AuthManager
from campaign_manager import CampaignManager
from database import init_db
from config import DB_PATH

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "phishsim.db"
TOKENS = {}
LOCK = threading.Lock()


def manager_for(token):
    with LOCK:
        item = TOKENS.get(token)
    if not item:
        return None
    username, expires_at = item
    if time.time() >= expires_at:
        with LOCK:
            TOKENS.pop(token, None)
        return None
    return CampaignManager(DB, username)


class Handler(BaseHTTPRequestHandler):
    server_version = "PhishSimLocal/1.0"

    def log_message(self, fmt, *args):
        # Avoid writing participant identifiers or request payloads to console logs.
        print("[PhishSim API] " + (fmt % args))

    def _send(self, status, payload):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)

    def _body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > 16_384:
            raise ValueError("حجم الطلب أكبر من المسموح.")
        raw = self.rfile.read(length) if length else b"{}"
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("صيغة الطلب غير صحيحة.")
        return value

    def _auth(self):
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return None
        return manager_for(header[7:].strip())

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            return self._send(200, {"ok": True, "app": "PhishSim"})
        manager = self._auth()
        if not manager:
            return self._send(401, {"error": "يلزم تسجيل الدخول."})
        try:
            if path == "/api/campaigns":
                return self._send(200, {"campaigns": manager.get_all_campaigns()})
            if path == "/api/reports":
                return self._send(200, {"reports": manager.get_reports()})
            return self._send(404, {"error": "المسار غير موجود."})
        except Exception:
            return self._send(500, {"error": "حدث خطأ داخلي."})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            data = self._body()
            if path == "/api/setup":
                auth = AuthManager(DB)
                if auth.has_users():
                    return self._send(409, {"error": "تم إعداد المشرف مسبقاً."})
                auth.create_admin(data.get("username"), data.get("password"))
                return self._send(201, {"ok": True})
            if path == "/api/login":
                auth = AuthManager(DB)
                if not auth.has_users():
                    return self._send(409, {"error": "يجب إعداد حساب المشرف أولاً."})
                if not auth.login(data.get("username"), data.get("password")):
                    return self._send(401, {"error": "بيانات الدخول غير صحيحة أو الحساب مقفل مؤقتاً."})
                token = secrets.token_urlsafe(32)
                with LOCK:
                    TOKENS[token] = (auth.username, time.time() + 8 * 60 * 60)
                return self._send(200, {"token": token, "username": auth.username})
            if path == "/api/logout":
                header = self.headers.get("Authorization", "")
                token = header[7:].strip() if header.startswith("Bearer ") else ""
                with LOCK:
                    TOKENS.pop(token, None)
                return self._send(200, {"ok": True})
            manager = self._auth()
            if not manager:
                return self._send(401, {"error": "يلزم تسجيل الدخول."})
            if path == "/api/campaigns":
                cid = manager.create_campaign({"name": data.get("name"), "url": data.get("url")})
                return self._send(201, {"id": cid})
            if path == "/api/events":
                manager.record_event(data.get("campaign_id"), data.get("participant_ref"), data.get("event_type"))
                return self._send(201, {"ok": True})
            return self._send(404, {"error": "المسار غير موجود."})
        except (ValueError, RuntimeError) as exc:
            return self._send(400, {"error": str(exc)})
        except Exception:
            return self._send(500, {"error": "حدث خطأ داخلي."})

    def do_PATCH(self):
        manager = self._auth()
        if not manager:
            return self._send(401, {"error": "يلزم تسجيل الدخول."})
        try:
            data = self._body()
            cid = int(data.get("campaign_id"))
            action = data.get("action")
            if action == "pause": manager.pause_campaign(cid)
            elif action == "resume": manager.resume_campaign(cid)
            elif action == "complete": manager.complete_campaign(cid)
            else: return self._send(400, {"error": "الإجراء غير صالح."})
            return self._send(200, {"ok": True})
        except (ValueError, RuntimeError) as exc:
            return self._send(400, {"error": str(exc)})
        except Exception:
            return self._send(500, {"error": "حدث خطأ داخلي."})


def main():
    init_db(DB)
    host = "0.0.0.0"
    port = 8765
    print("PhishSim API running on port 8765 (trusted LAN only).")
    print("Do not port-forward this service or expose it to the public internet.")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
