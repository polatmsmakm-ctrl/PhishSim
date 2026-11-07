import getpass
import sys
from pathlib import Path
from config import APP_NAME, DB_PATH
from database import init_db, backup_database
from campaign_manager import CampaignManager
from dashboard import Dashboard
from auth import AuthManager


def _read_campaign_id():
    raw = input("رقم الحملة: ").strip()
    if not raw.isdigit() or int(raw) < 1:
        raise ValueError("أدخل رقم حملة صحيحاً.")
    return int(raw)


def _print_reports(manager):
    reports = manager.get_reports()
    if not reports:
        print("لا توجد تقارير.")
        return
    for r in reports:
        print(f'#{r["id"]} {r["name"]}: مشاركون {r["participants"]} | نقرات {r["clicks"]} | '
              f'بلاغات {r["reports"]} | مبلّغون فريدون {r["unique_reporters"]} | '
              f'معدل الاكتشاف {r["discovery_rate"]}%')


def main():
    init_db(DB_PATH)
    auth = AuthManager(DB_PATH)

    if not auth.has_users():
        print(f"مرحباً بك في {APP_NAME}. إعداد أول حساب مشرف.")
        while True:
            username = input("اسم المشرف: ").strip()
            password = getpass.getpass("كلمة مرور جديدة (12 حرفاً على الأقل): ")
            confirm = getpass.getpass("أعد كتابة كلمة المرور: ")
            if password != confirm:
                print("كلمتا المرور غير متطابقتين.")
                continue
            try:
                auth.create_admin(username, password)
                print("تم إنشاء حساب المشرف.")
                break
            except (ValueError, RuntimeError) as exc:
                print(f"تعذر إنشاء الحساب: {exc}")

    authenticated = False
    for _ in range(3):
        username = input("اسم المستخدم: ").strip()
        password = getpass.getpass("كلمة المرور: ")
        if auth.login(username, password):
            authenticated = True
            break
        print("بيانات الدخول غير صحيحة أو الحساب مقفل مؤقتاً.")
    if not authenticated:
        print("تعذر تسجيل الدخول. إذا تجاوزت 5 محاولات فانتظر 15 دقيقة.")
        return

    manager = CampaignManager(DB_PATH, auth.username)
    try:
        while True:
            print(f"\n=== {APP_NAME} ===")
            print("1. إنشاء حملة تدريبية (مسودة)")
            print("2. عرض الحملات")
            print("3. إيقاف حملة نشطة")
            print("4. تفعيل مسودة / استئناف حملة")
            print("5. تسجيل تفاعل تجريبي")
            print("6. التقارير")
            print("7. حذف حملة")
            print("8. إكمال حملة")
            print("9. تصدير التقارير CSV")
            print("10. إنشاء نسخة احتياطية")
            print("11. خروج")
            choice = input("اختر: ").strip()

            try:
                if choice == "1":
                    name = input("اسم الحملة: ").strip()
                    url = input("رابط صفحة التدريب (على نطاق تملكه): ").strip()
                    cid = manager.create_campaign({"name": name, "url": url})
                    print(f"تم إنشاء الحملة #{cid} كمسودة. راجع الرابط قبل تفعيلها.")
                elif choice == "2":
                    Dashboard(manager).show_dashboard()
                elif choice == "3":
                    manager.pause_campaign(_read_campaign_id())
                    print("تم إيقاف الحملة.")
                elif choice == "4":
                    manager.resume_campaign(_read_campaign_id())
                    print("تم تفعيل / استئناف الحملة.")
                elif choice == "5":
                    cid = _read_campaign_id()
                    ref = input("معرّف مشارك تجريبي غير حقيقي: ").strip()
                    kind = input("نوع التفاعل (click/report): ").strip().lower()
                    manager.record_event(cid, ref, kind)
                    print("تم تسجيل التفاعل التجريبي.")
                elif choice == "6":
                    _print_reports(manager)
                elif choice == "7":
                    confirm = input("اكتب DELETE للتأكيد: ").strip()
                    if confirm == "DELETE":
                        manager.delete_campaign(_read_campaign_id())
                        print("تم حذف الحملة.")
                    else:
                        print("تم إلغاء الحذف.")
                elif choice == "8":
                    manager.complete_campaign(_read_campaign_id())
                    print("تم إكمال الحملة وأُغلق تسجيل التفاعلات.")
                elif choice == "9":
                    default = Path(DB_PATH).parent / "reports.csv"
                    destination = input(f"مسار الملف [{default}]: ").strip() or str(default)
                    print(f"تم تصدير التقارير إلى: {manager.export_reports_csv(destination)}")
                elif choice == "10":
                    print(f"تم إنشاء النسخة الاحتياطية: {backup_database(DB_PATH)}")
                elif choice == "11":
                    print("إلى اللقاء.")
                    break
                else:
                    print("اختيار غير صحيح.")
            except (ValueError, RuntimeError, OSError) as exc:
                print(f"تعذر تنفيذ العملية: {exc}")
    finally:
        auth.logout()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nتم إيقاف البرنامج.")
        sys.exit(0)
