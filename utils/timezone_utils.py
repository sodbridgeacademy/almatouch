from datetime import timezone, timedelta
from zoneinfo import ZoneInfo
from flask import session
from models import Organization


def to_local_time(dt, tz_name="Africa/Lagos"):
    if not dt:
        return None

    if not tz_name:
        tz_name = "Africa/Lagos"  # fallback safety

    return dt.astimezone(ZoneInfo(tz_name))

# tz for analytics
def format_datetime(dt, org):
    return to_local_time(dt, org.timezone)

def get_org():
    org_id = session.get("org_id")
    return Organization.query.get(org_id)