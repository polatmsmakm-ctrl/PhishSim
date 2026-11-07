import csv
import tempfile
import unittest
from pathlib import Path
from database import init_db, backup_database
from campaign_manager import CampaignManager
from auth import AuthManager


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "test.db"
        init_db(self.db)
        self.manager = CampaignManager(self.db, "tester")

    def tearDown(self):
        self.tmp.cleanup()

    def make_active_campaign(self):
        cid = self.manager.create_campaign({"name": "حملة توعية", "url": "https://training.example.test"})
        self.manager.resume_campaign(cid)
        return cid

    def test_campaign_and_unique_discovery_rate(self):
        cid = self.make_active_campaign()
        self.manager.record_event(cid, "participant-1", "click")
        self.manager.record_event(cid, "participant-2", "report")
        self.manager.record_event(cid, "participant-2", "report")
        report = self.manager.get_reports()[0]
        self.assertEqual(report["clicks"], 1)
        self.assertEqual(report["reports"], 2)
        self.assertEqual(report["participants"], 2)
        self.assertEqual(report["unique_reporters"], 1)
        self.assertEqual(report["discovery_rate"], 50.0)

    def test_campaign_must_start_as_draft(self):
        with self.assertRaises(ValueError):
            self.manager.create_campaign({"name": "No", "url": "https://training.example.test", "status": "active"})

    def test_pause_blocks_events_and_resume_works(self):
        cid = self.make_active_campaign()
        self.manager.pause_campaign(cid)
        with self.assertRaises(ValueError):
            self.manager.record_event(cid, "p1", "click")
        self.manager.resume_campaign(cid)
        self.manager.record_event(cid, "p1", "click")

    def test_completed_campaign_cannot_be_reopened(self):
        cid = self.make_active_campaign()
        self.manager.complete_campaign(cid)
        with self.assertRaises(ValueError):
            self.manager.resume_campaign(cid)
        with self.assertRaises(ValueError):
            self.manager.record_event(cid, "p1", "click")

    def test_auth_and_lockout(self):
        auth = AuthManager(self.db)
        auth.create_admin("administrator", "a-long-test-password")
        self.assertTrue(auth.login("administrator", "a-long-test-password"))
        auth.logout()
        for _ in range(5):
            self.assertFalse(auth.login("administrator", "wrong-password"))
        self.assertFalse(auth.login("administrator", "a-long-test-password"))

    def test_duplicate_admin_rejected(self):
        auth = AuthManager(self.db)
        auth.create_admin("administrator", "a-long-test-password")
        with self.assertRaises(RuntimeError):
            auth.create_admin("another-admin", "another-long-password")

    def test_invalid_urls(self):
        for url in ("not-a-url", "javascript:alert(1)", "https://user:pass@example.com", "https://bad host.test"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.manager.create_campaign({"name": "Bad", "url": url})

    def test_csv_export_and_backup(self):
        cid = self.make_active_campaign()
        self.manager.record_event(cid, "p1", "report")
        csv_path = self.root / "reports.csv"
        self.manager.export_reports_csv(csv_path)
        with csv_path.open(encoding="utf-8-sig") as f:
            self.assertEqual(len(list(csv.DictReader(f))), 1)
        backup = backup_database(self.db, self.root / "backup.db")
        self.assertTrue(Path(backup).exists())


if __name__ == "__main__":
    unittest.main()
