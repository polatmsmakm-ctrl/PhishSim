import csv
from datetime import datetime, timezone
from pathlib import Path
from database import get_db_connection, log_audit
from utils.validators import validate_campaign_data

_STATUSES = {"draft", "active", "paused", "completed"}


class CampaignManager:
    def __init__(self, db_path=None, username="admin"):
        self.db_path = db_path
        self.username = username

    def _require_id(self, campaign_id):
        if isinstance(campaign_id, bool) or not isinstance(campaign_id, int) or campaign_id < 1:
            raise ValueError("رقم الحملة غير صالح.")

    def create_campaign(self, campaign_data):
        validate_campaign_data(campaign_data)
        name = campaign_data["name"].strip()
        url = campaign_data["url"].strip()
        # A campaign must be reviewed explicitly before activation.
        status = campaign_data.get("status", "draft")
        if status != "draft":
            raise ValueError("يجب إنشاء الحملة كمسودة ثم مراجعتها وتفعيلها بشكل منفصل.")
        with get_db_connection(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO campaigns(name, training_url, status) VALUES (?, ?, 'draft')",
                (name, url)
            )
            campaign_id = cur.lastrowid
        log_audit(self.username, "campaign_created", f"campaign_id={campaign_id}", self.db_path)
        return campaign_id

    def edit_campaign(self, campaign_id, updates):
        self._require_id(campaign_id)
        allowed = {"name", "url", "status"}
        if not isinstance(updates, dict) or not updates or set(updates) - allowed:
            raise ValueError("التعديلات غير صالحة.")
        with get_db_connection(self.db_path) as conn:
            row = conn.execute("SELECT * FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
            if not row:
                raise ValueError("الحملة غير موجودة.")
            name = str(updates.get("name", row["name"])).strip()
            url = str(updates.get("url", row["training_url"])).strip()
            status = updates.get("status", row["status"])
            validate_campaign_data({"name": name, "url": url})
            if status not in _STATUSES:
                raise ValueError("حالة الحملة غير صالحة.")
            if row["status"] == "completed" and status != "completed":
                raise ValueError("لا يمكن إعادة فتح حملة مكتملة.")
            conn.execute(
                "UPDATE campaigns SET name=?, training_url=?, status=?, updated_at=? WHERE id=?",
                (name, url, status, datetime.now(timezone.utc).isoformat(), campaign_id)
            )
        log_audit(self.username, "campaign_updated", f"campaign_id={campaign_id};status={status}", self.db_path)

    def delete_campaign(self, campaign_id):
        self._require_id(campaign_id)
        with get_db_connection(self.db_path) as conn:
            cur = conn.execute("DELETE FROM campaigns WHERE id=?", (campaign_id,))
            if cur.rowcount == 0:
                raise ValueError("الحملة غير موجودة.")
        log_audit(self.username, "campaign_deleted", f"campaign_id={campaign_id}", self.db_path)

    def pause_campaign(self, campaign_id):
        self._require_id(campaign_id)
        with get_db_connection(self.db_path) as conn:
            row = conn.execute("SELECT status FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
            if not row:
                raise ValueError("الحملة غير موجودة.")
            if row["status"] != "active":
                raise ValueError("يمكن إيقاف الحملة النشطة فقط.")
        self.edit_campaign(campaign_id, {"status": "paused"})

    def resume_campaign(self, campaign_id):
        self._require_id(campaign_id)
        with get_db_connection(self.db_path) as conn:
            row = conn.execute("SELECT status FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
            if not row:
                raise ValueError("الحملة غير موجودة.")
            if row["status"] not in ("draft", "paused"):
                raise ValueError("يمكن تفعيل المسودة أو استئناف الحملة المتوقفة فقط.")
        self.edit_campaign(campaign_id, {"status": "active"})

    def complete_campaign(self, campaign_id):
        self._require_id(campaign_id)
        with get_db_connection(self.db_path) as conn:
            row = conn.execute("SELECT status FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
            if not row:
                raise ValueError("الحملة غير موجودة.")
            if row["status"] not in ("active", "paused"):
                raise ValueError("لا يمكن إكمال هذه الحملة من حالتها الحالية.")
        self.edit_campaign(campaign_id, {"status": "completed"})

    def get_all_campaigns(self):
        with get_db_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, name, training_url, status, created_at, updated_at FROM campaigns ORDER BY id DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def record_event(self, campaign_id, participant_ref, event_type):
        self._require_id(campaign_id)
        if event_type not in ("click", "report"):
            raise ValueError("نوع التفاعل غير صالح.")
        participant_ref = str(participant_ref or "").strip()
        if not participant_ref or len(participant_ref) > 80:
            raise ValueError("المعرّف التجريبي مطلوب وبحد أقصى 80 حرفاً.")
        with get_db_connection(self.db_path) as conn:
            row = conn.execute("SELECT status FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
            if not row:
                raise ValueError("الحملة غير موجودة.")
            if row["status"] != "active":
                raise ValueError("لا يمكن تسجيل تفاعل إلا لحملة نشطة.")
            conn.execute(
                "INSERT INTO events(campaign_id, participant_ref, event_type) VALUES (?, ?, ?)",
                (campaign_id, participant_ref, event_type)
            )
        log_audit(self.username, f"event_{event_type}", f"campaign_id={campaign_id}", self.db_path)

    def get_reports(self):
        with get_db_connection(self.db_path) as conn:
            rows = conn.execute("""
                SELECT c.id, c.name,
                       COUNT(CASE WHEN e.event_type='click' THEN 1 END) AS clicks,
                       COUNT(CASE WHEN e.event_type='report' THEN 1 END) AS reports,
                       COUNT(DISTINCT e.participant_ref) AS participants,
                       COUNT(DISTINCT CASE WHEN e.event_type='report' THEN e.participant_ref END) AS unique_reporters
                FROM campaigns c
                LEFT JOIN events e ON e.campaign_id=c.id
                GROUP BY c.id, c.name ORDER BY c.id DESC
            """).fetchall()
        output = []
        for r in rows:
            participants = r["participants"] or 0
            reporters = r["unique_reporters"] or 0
            rate = round((reporters / participants) * 100, 2) if participants else 0.0
            output.append({
                "id": r["id"], "name": r["name"], "clicks": r["clicks"] or 0,
                "reports": r["reports"] or 0, "participants": participants,
                "unique_reporters": reporters, "discovery_rate": min(rate, 100.0)
            })
        return output

    def export_reports_csv(self, destination):
        reports = self.get_reports()
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=[
                "id", "name", "clicks", "reports", "participants", "unique_reporters", "discovery_rate"
            ])
            writer.writeheader()
            for report in reports:
                safe = dict(report)
                # Prevent spreadsheet formula injection in text fields.
                if isinstance(safe["name"], str) and safe["name"].startswith(("=", "+", "-", "@", "\t", "\r")):
                    safe["name"] = "'" + safe["name"]
                writer.writerow(safe)
        log_audit(self.username, "reports_exported", f"path={path.name}", self.db_path)
        return str(path)
