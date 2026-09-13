from datetime import date
from apscheduler.schedulers.background import BackgroundScheduler
from services.remember_service import send_prepared_remember_messages
from services.notification_service import (
    process_remember_notifications
)


# ============================================================
# 🚀 SCHEDULER
# ============================================================

scheduler = BackgroundScheduler(
    timezone="Africa/Lagos"
)


# ============================================================
# 🧠 REMEMBER PROCESSOR
# ============================================================

def process_remembers(target_date=None):

    if target_date is None:
        target_date = date.today()

    print(
        f"📅 Processing Remembers for {target_date}"
    )

    report = send_prepared_remember_messages(
        target_date
    )

    found_count = len(
        report["found_remembers"]
    )

    eligible_count = len(
        report["eligible_recipients"]
    )

    already_sent_count = len(
        report["already_sent"]
    )

    sent_count = 0
    failed_count = 0

    for result in report["results"]:

        status = result.get("send_status")

        if status == "sent":
            sent_count += 1

        elif status == "failed":
            failed_count += 1

    print(
        f"📅 Found: {found_count} Remember"
    )

    print(
        f"👥 Eligible recipients: {eligible_count}"
    )

    print(
        f"📨 Sent: {sent_count}"
    )

    print(
        f"✅ Already sent: {already_sent_count}"
    )

    print(
        f"❌ Failed: {failed_count}"
    )

    return report


# ============================================================
# 🔄 SCHEDULED JOB
# ============================================================

def run_remember_job():

    # Import app here to avoid circular import
    from app import app

    with app.app_context():

        try:

            process_remembers()

            notification_report = (
                process_remember_notifications()
            )

            print(
                f"🔔 Notifications created: "
                f"{notification_report['created']}"
            )

            print(
                f"🔔 Notifications skipped: "
                f"{notification_report['skipped']}"
            )

        except Exception as exc:

            print(
                f"❌ Remember automation error: {exc}"
            )


# ============================================================
# 🚀 START SCHEDULER
# ============================================================

def start_scheduler():

    if scheduler.running:

        print(
            "⚠️ AlmaTouch Scheduler already running"
        )

        return

    scheduler.add_job(
        run_remember_job,
        trigger="interval",
        minutes=1,
        id="remember_processor",
        replace_existing=True,
        max_instances=1,
        coalesce=True
    )

    scheduler.start()

    print(
        "🚀 AlmaTouch Scheduler Started"
    )


# ============================================================
# 🔔 REMEMBER NOTIFICATION PROCESSOR
# ============================================================

def process_remember_notifications_job(target_date=None):

    if target_date is None:
        target_date = date.today()

    print(
        f"🔔 Processing Remember notifications for {target_date}"
    )

    report = process_remember_notifications(
        target_date
    )

    print(
        f"🔔 Notifications created: {report['created']}"
    )

    print(
        f"🔔 Notifications skipped: {report['skipped']}"
    )

    return report