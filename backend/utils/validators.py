import ipaddress
import re
from urllib.parse import urlsplit


def validate_campaign_data(data):
    if not isinstance(data, dict):
        raise ValueError("بيانات الحملة غير صحيحة.")
    name = str(data.get("name", "")).strip()
    url = str(data.get("url", "")).strip()
    if not name:
        raise ValueError("اسم الحملة مطلوب.")
    if len(name) > 100:
        raise ValueError("اسم الحملة طويل جداً (الحد 100 حرف).")
    if not url or len(url) > 500:
        raise ValueError("رابط صفحة التدريب مطلوب وبحد أقصى 500 حرف.")
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("صيغة الرابط غير صحيحة.") from exc
    if parsed.scheme.lower() not in ("http", "https") or not host:
        raise ValueError("أدخل رابط HTTP أو HTTPS صحيحاً.")
    if parsed.username or parsed.password:
        raise ValueError("لا تضع بيانات دخول داخل الرابط.")
    if any(ch.isspace() for ch in url) or not re.fullmatch(r"[A-Za-z0-9.-]+", host) and not _is_ip(host):
        raise ValueError("اسم النطاق في الرابط غير صالح.")
    return True


def _is_ip(host):
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def validate_user_input(value, field="القيمة"):
    value = str(value or "").strip()
    if not value:
        raise ValueError(f"{field} مطلوبة.")
    return value
