from campaign_manager import CampaignManager


class Dashboard:
    def __init__(self, manager=None):
        self.manager = manager or CampaignManager()

    def show_dashboard(self):
        campaigns = self.manager.get_all_campaigns()
        reports = {r["id"]: r for r in self.manager.get_reports()}
        print("\n" + "=" * 76)
        print("PhishSim | لوحة التحكم")
        print("=" * 76)
        if not campaigns:
            print("لا توجد حملات حتى الآن.")
            return
        for c in campaigns:
            r = reports[c["id"]]
            status = {"draft": "مسودة", "active": "نشطة", "paused": "متوقفة", "completed": "مكتملة"}[c["status"]]
            print(f'#{c["id"]} | {c["name"]} | الحالة: {status}')
            print(f'   المشاركون: {r["participants"]} | النقرات: {r["clicks"]} | البلاغات: {r["reports"]}')
            print(f'   المبلّغون الفريدون: {r["unique_reporters"]} | معدل الاكتشاف: {r["discovery_rate"]}%')
            print(f'   رابط التدريب: {c["training_url"]}')
        print("=" * 76)
