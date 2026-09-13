from datetime import date

from extensions import db
from models import (
    Notification,
    Organization,
    User,
)
from services.remember_service import (
    get_user_upcoming_remembers,
    get_org_upcoming_remembers,
)


# ============================================
# NOTIFICATION TIMING
# ============================================

ORG_NOTIFICATION_DAYS = 7
USER_NOTIFICATION_DAYS = 2


# ============================================
# CREATE NOTIFICATION
# ============================================

def create_notification(
    user_id,
    org_id,
    title,
    message,
    notification_type="system",
    context="user",
    related_url=None,
    remember_id=None,
    event_id=None,
    occurrence_date=None,
):
    """
    Create a notification if the same notification
    has not already been created for this occurrence.
    """

    query = Notification.query.filter_by(
        user_id=user_id,
        org_id=org_id,
        context=context,
        notification_type=notification_type,
        occurrence_date=occurrence_date,
    )

    if remember_id is not None:
        query = query.filter_by(
            remember_id=remember_id
        )

    elif event_id is not None:
        query = query.filter_by(
            event_id=event_id
        )

    else:
        query = query.filter(
            Notification.remember_id.is_(None),
            Notification.event_id.is_(None)
        )

    existing = query.first()

    if existing:
        return existing, False

    notification = Notification(
        user_id=user_id,
        org_id=org_id,
        title=title,
        message=message,
        notification_type=notification_type,
        context=context,
        related_url=related_url,
        remember_id=remember_id,
        event_id=event_id,
        occurrence_date=occurrence_date,
        is_read=False,
    )

    db.session.add(notification)
    db.session.commit()

    return notification, True


# ============================================
# PROCESS REMEMBER NOTIFICATIONS
# ============================================

def process_remember_notifications(target_date=None):
    """
    Create notifications for upcoming Remembers.

    Organization context:
        7 days before

    User context:
        2 days before
    """

    if target_date is None:
        target_date = date.today()

    created_count = 0
    skipped_count = 0

    organizations = Organization.query.filter_by(
        is_active=True
    ).all()

    for org in organizations:



        # ========================================
        # ORGANIZATION CONTEXT
        # ========================================

        org_remembers = get_org_upcoming_remembers(
            org,
            target_date=target_date
        )

        organization_users = User.query.filter(
            User.org_id == org.id,
            User.is_active.is_(True),
            User.role.in_(["owner", "admin"])
        ).all()

        for item in org_remembers:

            days_until = (
                item["date"] - target_date
            ).days

            if days_until < 0:
                continue

            if days_until > ORG_NOTIFICATION_DAYS:
                continue

            # ------------------------------------
            # CREATE ORGANIZATION NOTIFICATION
            # ------------------------------------

            for user in organization_users:

                title = f"{item['name']} is coming up"

                message = (
                    f"{item['name']} is coming up "
                    f"on {item['date'].strftime('%B %d, %Y')}."
                )

                _, created = create_notification(
                    user_id=user.id,
                    org_id=org.id,
                    title=title,
                    message=message,
                    notification_type="remember",
                    context="organization",
                    remember_id=item.get("remember_id"),
                    occurrence_date=item["date"],
                )

                if created:
                    created_count += 1
                else:
                    skipped_count += 1


        # ========================================
        # USER CONTEXT
        # ========================================

        for user in users:

            user_remembers = get_user_upcoming_remembers(
                user,
                org,
                target_date=target_date
            )

            for item in user_remembers:

                days_until = (
                    item["date"] - target_date
                ).days

                if days_until < 0:
                    continue

                if days_until > USER_NOTIFICATION_DAYS:
                    continue

                title = f"{item['name']} is coming up"

                message = (
                    f"{item['name']} is coming up "
                    f"on {item['date'].strftime('%B %d, %Y')}."
                )

                _, created = create_notification(
                    user_id=user.id,
                    org_id=org.id,
                    title=title,
                    message=message,
                    notification_type="remember",
                    context="user",
                    remember_id=item.get("remember_id"),
                    occurrence_date=item["date"],
                )

                if created:
                    created_count += 1
                else:
                    skipped_count += 1

    return {
        "created": created_count,
        "skipped": skipped_count,
    }

