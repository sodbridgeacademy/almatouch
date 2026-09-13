from datetime import date
from utils.email_sender import send_email
from extensions import db

from models import (
    Organization,
    Remember,
    UserRemember,
    User,
    MessageLog
)


# ============================================================
# 🔍 GET ACTIVE ORGANIZATIONS
# ============================================================

def get_active_organizations():
    """
    Return all active organizations.
    """
    return Organization.query.filter_by(
        is_active=True
    ).all()


# ============================================================
# 📅 CHECK WHETHER A REMEMBER OCCURS ON A DATE
# ============================================================

def remember_occurs_on(remember, target_date):
    """
    Determine whether a Remember occurs on target_date.

    Recurring Remembers use only month/day.
    Non-recurring Remembers use the exact stored date.
    """

    if not remember.is_active:
        return False

    if remember.is_recurring:

        return (
            remember.date.month == target_date.month
            and remember.date.day == target_date.day
        )

    return remember.date == target_date


# ============================================================
# 🧠 GET DUE ORGANIZATION REMEMBERS
# ============================================================

def get_due_remembers(target_date=None):
    """
    Return active organization Remembers that occur
    on the target date.

    Each result contains:
        - remember
        - organization
        - occurrence_date
    """

    if target_date is None:
        target_date = date.today()

    results = []

    organizations = get_active_organizations()

    for org in organizations:

        remembers = Remember.query.filter_by(
            org_id=org.id,
            is_active=True
        ).all()

        for remember in remembers:

            if not remember_occurs_on(
                remember,
                target_date
            ):
                continue

            results.append({
                "remember": remember,
                "organization": org,
                "occurrence_date": target_date
            })

    return results


# ============================================================
# 👥 GET RECIPIENTS
# ============================================================

def get_remember_recipients(org):
    """
    Return active users in the organization who are
    currently opted in to notifications.

    This is the initial recipient rule for organization
    Remembers.
    """

    return User.query.filter_by(
        org_id=org.id,
        is_active=True,
        receive_notifications=True
    ).all()


# ============================================================
# 🛑 DUPLICATE CHECK
# ============================================================

def remember_message_already_logged(
    user_id,
    remember_id,
    occurrence_date,
    channel="email"
):
    """
    Check whether a message has already been logged for
    this user, Remember occurrence and channel.
    """

    existing = MessageLog.query.filter_by(
        user_id=user_id,
        remember_id=remember_id,
        occurrence_date=occurrence_date,
        channel=channel
    ).first()

    return existing is not None


# ============================================================
# 📦 PREPARE REMEMBER MESSAGES
# ============================================================

def prepare_remember_messages(target_date=None):
    """
    Prepare Remember messages for a target date.

    Returns:
        {
            "found_remembers": [...],
            "eligible_recipients": [...],
            "messages": [...],
            "already_sent": [...]
        }
    """

    if target_date is None:
        target_date = date.today()

    found_remembers = []
    eligible_recipients = []
    messages = []
    already_sent = []

    due_remembers = get_due_remembers(
        target_date
    )

    for item in due_remembers:

        remember = item["remember"]
        org = item["organization"]
        occurrence_date = item["occurrence_date"]

        # ---------------------------------
        # REMEMBER FOUND
        # ---------------------------------
        found_remembers.append(item)

        recipients = get_remember_recipients(
            org
        )

        for user in recipients:

            eligible_recipients.append({
                "organization": org,
                "remember": remember,
                "occurrence_date": occurrence_date,
                "recipient": user,
                "channel": "email"
            })

            # ---------------------------------
            # DUPLICATE CHECK
            # ---------------------------------
            if remember_message_already_logged(
                user_id=user.id,
                remember_id=remember.id,
                occurrence_date=occurrence_date,
                channel="email"
            ):

                already_sent.append({
                    "organization": org,
                    "remember": remember,
                    "occurrence_date": occurrence_date,
                    "recipient": user,
                    "channel": "email"
                })

                continue

            messages.append({
                "organization": org,
                "remember": remember,
                "occurrence_date": occurrence_date,
                "recipient": user,
                "channel": "email"
            })

    return {
        "found_remembers": found_remembers,
        "eligible_recipients": eligible_recipients,
        "messages": messages,
        "already_sent": already_sent
    }

# ============================================================
# 💬 GET REMEMBER TEMPLATE
# ============================================================

def get_remember_template(
    remember,
    channel="email"
):
    """
    Get the message template for a Remember/channel.
    """

    for template in remember.message_templates:

        if template.channel == channel:
            return template

    return None

# ============================================================
# 🧩 RENDER MESSAGE TEMPLATE
# ============================================================

def render_remember_template(
    template,
    organization,
    recipient,
    remember
):
    """
    Render a Remember message template using basic
    AlmaTouch placeholders.
    """

    if not template:
        return None

    subject = template.subject or ""
    body = template.body_template or ""

    replacements = {
        "{{ organization.name }}": organization.name,
        "{{ recipient.first_name }}": recipient.first_name or "",
        "{{ recipient.last_name }}": recipient.last_name or "",
        "{{ recipient.full_name }}": (
            f"{recipient.first_name or ''} "
            f"{recipient.last_name or ''}"
        ).strip(),
        "{{ recipient.email }}": recipient.email,
        "{{ remember.name }}": remember.name,
        "{{ remember.date }}": remember.date.strftime("%B %d"),
    }

    for placeholder, value in replacements.items():
        subject = subject.replace(
            placeholder,
            value
        )

        body = body.replace(
            placeholder,
            value
        )

    return {
        "subject": subject,
        "body": body
    }


# ============================================================
# 📦 PREPARE RENDERED REMEMBER MESSAGES
# ============================================================
def prepare_rendered_remember_messages(target_date=None):
    """
    Prepare complete Remember messages.

    Nothing is sent and nothing is logged here.
    """

    if target_date is None:
        target_date = date.today()

    prepared = prepare_remember_messages(
        target_date
    )

    rendered_messages = []

    for item in prepared["messages"]:

        organization = item["organization"]
        remember = item["remember"]
        recipient = item["recipient"]
        channel = item["channel"]

        template = get_remember_template(
            remember=remember,
            channel=channel
        )

        if not template:

            rendered_messages.append({
                **item,
                "template": None,
                "subject": None,
                "body": None,
                "status": "no_template"
            })

            continue

        rendered = render_remember_template(
            template=template,
            organization=organization,
            recipient=recipient,
            remember=remember
        )

        rendered_messages.append({
            **item,
            "template": template,
            "subject": rendered["subject"],
            "body": rendered["body"],
            "status": "ready"
        })

    return {
        **prepared,
        "rendered_messages": rendered_messages
    }




# ============================================================
# 📤 SEND + LOG ONE REMEMBER MESSAGE
# ============================================================
def send_remember_message(item):
    """
    Send one prepared Remember message and create/update
    its MessageLog.

    Returns:
        dict containing status and message details.
    """

    organization = item["organization"]
    remember = item["remember"]
    recipient = item["recipient"]
    occurrence_date = item["occurrence_date"]
    channel = item["channel"]
    template = item["template"]

    subject = item["subject"]
    body = item["body"]

    # --------------------------------------------------------
    # SAFETY CHECK
    # --------------------------------------------------------
    if item["status"] != "ready":
        return {
            **item,
            "send_status": item["status"],
            "error": "Message is not ready to be sent."
        }

    # --------------------------------------------------------
    # FIND EXISTING LOG
    # --------------------------------------------------------
    existing_log = MessageLog.query.filter_by(
        user_id=recipient.id,
        remember_id=remember.id,
        occurrence_date=occurrence_date,
        channel=channel
    ).first()

    # Already successfully sent
    if existing_log and existing_log.status == "sent":
        return {
            **item,
            "send_status": "already_sent",
            "log": existing_log
        }

    # --------------------------------------------------------
    # SEND
    # --------------------------------------------------------
    try:

        if channel == "email":

            send_email(
                to=recipient.email,
                subject=subject,
                body=body
            )

        else:

            return {
                **item,
                "send_status": "unsupported_channel",
                "error": f"Channel '{channel}' is not supported yet."
            }

        # ----------------------------------------------------
        # LOG SUCCESS
        # ----------------------------------------------------
        if existing_log:

            existing_log.template_id = (
                template.id if template else None
            )

            existing_log.message_content = body
            existing_log.subject = subject
            existing_log.status = "sent"

        else:

            existing_log = MessageLog(
                user_id=recipient.id,
                org_id=organization.id,
                remember_id=remember.id,
                template_id=(
                    template.id if template else None
                ),
                message_content=body,
                subject=subject,
                channel=channel,
                status="sent",
                occurrence_date=occurrence_date
            )

            db.session.add(existing_log)

        db.session.commit()

        return {
            **item,
            "send_status": "sent",
            "log": existing_log
        }

    except Exception as exc:

        db.session.rollback()

        return {
            **item,
            "send_status": "failed",
            "error": str(exc)
        }




# ============================================================
# 📤 SEND + LOG REMEMBER MESSAGES
# ============================================================
def send_prepared_remember_messages(target_date=None):
    """
    Prepare, send and log Remember messages.
    """

    if target_date is None:
        target_date = date.today()

    prepared = prepare_rendered_remember_messages(
        target_date
    )

    results = []

    for item in prepared["rendered_messages"]:

        result = send_remember_message(item)

        results.append(result)

    return {
        **prepared,
        "results": results
    }




# =================================
# USER DASHBOARD REMEMBERS
# =================================
def get_user_upcoming_remembers(user, org, target_date=None):
    """
    Return all upcoming Remembers relevant to a user
    from target_date through the end of the current year.

    Sources:
    - User birthday
    - User work anniversary
    - User-created reminders
    - Organization Remembers
    - Shared/public dates

    Returns a sorted list of dictionaries with:
        name
        date
        type
        source
        kind
    """

    if target_date is None:
        target_date = date.today()

    current_year = target_date.year

    reminders = []

    # =================================
    # PERSONAL SYSTEM REMEMBERS
    # =================================

    # Birthday
    if user.date_of_birth:
        try:
            birthday = date(
                current_year,
                user.date_of_birth.month,
                user.date_of_birth.day
            )

            if birthday >= target_date:
                reminders.append({
                    "name": "Your Birthday",
                    "date": birthday,
                    "type": "birthday",
                    "source": "personal",
                    "kind": "system"
                })

        except ValueError:
            # Handles February 29 in a non-leap year
            pass


    # Work anniversary
    if user.joined_date:
        try:
            work_anniversary = date(
                current_year,
                user.joined_date.month,
                user.joined_date.day
            )

            if work_anniversary >= target_date:
                reminders.append({
                    "name": "Your Work Anniversary",
                    "date": work_anniversary,
                    "type": "work_anniversary",
                    "source": "personal",
                    "kind": "system"
                })

        except ValueError:
            pass


    # =========================
    # USER-CREATED REMEMBERS
    # =========================

    user_remembers = UserRemember.query.filter_by(
        user_id=user.id,
        is_active=True
    ).all()

    for remember in user_remembers:

        if remember.is_recurring:

            try:
                occurrence_date = date(
                    current_year,
                    remember.date.month,
                    remember.date.day
                )
            except ValueError:
                continue

            if occurrence_date < target_date:
                continue

        else:

            occurrence_date = remember.date

            if occurrence_date < target_date:
                continue

        reminders.append({
            "name": remember.name,
            "date": occurrence_date,
            "type": remember.remember_type,
            "source": "personal",
            "kind": "user",

            # Needed by Edit/Delete
            "remember_id": remember.id,
            "original_date": remember.date.strftime("%Y-%m-%d"),
            "is_recurring": remember.is_recurring,
            "is_public": remember.is_public
        })


    # =================================
    # ORGANIZATION REMEMBERS
    # =================================

    org_remembers = Remember.query.filter_by(
        org_id=org.id,
        is_active=True
    ).all()

    for remember in org_remembers:

        try:
            occurrence_date = date(
                current_year,
                remember.date.month,
                remember.date.day
            )

        except ValueError:
            # Handles dates such as February 29
            # in a non-leap year.
            continue

        if occurrence_date < target_date:
            continue

        reminders.append({
            "name": remember.name,
            "date": occurrence_date,
            "type": remember.remember_type,
            "source": "organization",
            "kind": "organization"
        })


    # =================================
    # SHARED / PUBLIC REMEMBERS
    # =================================

    shared_remembers = [
        {
            "name": "Independence Day",
            "date": date(current_year, 10, 1),
            "type": "national",
            "source": "shared",
            "kind": "shared"
        },
        {
            "name": "Christmas Day",
            "date": date(current_year, 12, 25),
            "type": "holiday",
            "source": "shared",
            "kind": "shared"
        },
    ]

    for remember in shared_remembers:

        if remember["date"] >= target_date:
            reminders.append(remember)


    # =================================
    # SORT
    # =================================

    reminders.sort(
        key=lambda item: item["date"]
    )

    return reminders


# =================================
# ORGANIZATION DASHBOARD REMEMBERS
# =================================

# =================================
# ORGANIZATION DASHBOARD REMEMBERS
# =================================
def get_org_upcoming_remembers(org, target_date=None):
    """
    Return upcoming Remembers relevant to an organization.

    Sources:
    - Organization Remembers
    - Active member birthdays
    - Active member work anniversaries
    - Public/shared member Remembers
    - Shared/public dates

    Recurring dates are resolved to their next occurrence.

    Returns a sorted list of dictionaries with:
        name
        date
        type
        source
        kind
    """

    if target_date is None:
        target_date = date.today()

    current_year = target_date.year

    reminders = []

    # =================================
    # HELPER: NEXT ANNUAL OCCURRENCE
    # =================================

    def next_annual_occurrence(month, day):
        """
        Return the next occurrence of an annual date
        on or after target_date.
        """

        try:
            occurrence = date(
                current_year,
                month,
                day
            )

        except ValueError:
            # Handles February 29 in non-leap years.
            occurrence = date(
                current_year,
                month,
                28
            )

        if occurrence < target_date:

            try:
                occurrence = date(
                    current_year + 1,
                    month,
                    day
                )

            except ValueError:
                occurrence = date(
                    current_year + 1,
                    month,
                    28
                )

        return occurrence


    # =================================
    # ORGANIZATION REMEMBERS
    # =================================

    organization_remembers = Remember.query.filter_by(
        org_id=org.id,
        is_active=True
    ).all()

    for remember in organization_remembers:

        if remember.is_recurring:

            occurrence = next_annual_occurrence(
                remember.date.month,
                remember.date.day
            )

        else:

            occurrence = remember.date

            # Ignore expired one-time reminders.
            if occurrence < target_date:
                continue

        reminders.append({
            "name": remember.name,
            "date": occurrence,
            "type": remember.remember_type,
            "source": "organization",
            "kind": "organization",
            "remember_id": remember.id,
            "original_date": remember.date.strftime("%Y-%m-%d"),
            "is_recurring": remember.is_recurring
        })


    # =================================
    # ACTIVE MEMBER DATES
    # =================================

    members = User.query.filter_by(
        org_id=org.id,
        is_active=True
    ).all()

    for member in members:

        # ---------------------------------
        # BIRTHDAY
        # ---------------------------------

        if member.date_of_birth:

            birthday = next_annual_occurrence(
                member.date_of_birth.month,
                member.date_of_birth.day
            )

            reminders.append({
                "name": f"{member.first_name}'s Birthday",
                "date": birthday,
                "type": "birthday",
                "source": "member",
                "kind": "system",
                "user_id": member.id
            })


        # ---------------------------------
        # WORK ANNIVERSARY
        # ---------------------------------

        if member.joined_date:

            anniversary = next_annual_occurrence(
                member.joined_date.month,
                member.joined_date.day
            )

            reminders.append({
                "name": f"{member.first_name}'s Work Anniversary",
                "date": anniversary,
                "type": "work_anniversary",
                "source": "member",
                "kind": "system",
                "user_id": member.id
            })


    # =================================
    # PUBLIC MEMBER REMEMBERS
    # =================================

    public_member_remembers = (
        UserRemember.query
        .join(User, User.id == UserRemember.user_id)
        .filter(
            User.org_id == org.id,
            User.is_active == True,
            UserRemember.is_active == True,
            UserRemember.is_public == True
        )
        .all()
    )

    for remember in public_member_remembers:

        if remember.is_recurring:

            occurrence = next_annual_occurrence(
                remember.date.month,
                remember.date.day
            )

        else:

            occurrence = remember.date

            if occurrence < target_date:
                continue

        reminders.append({
            "name": f"{remember.user.first_name}'s {remember.name}",
            "date": occurrence,
            "type": remember.remember_type,
            "source": "member",
            "kind": "user",
            "user_id": remember.user_id,
            "remember_id": remember.id,
            "original_date": remember.date.strftime("%Y-%m-%d"),
            "is_recurring": remember.is_recurring
        })


    # =================================
    # SHARED / PUBLIC REMEMBERS
    # =================================

    if org.country and org.country.lower() == "nigeria":

        shared_remembers = [
            {
                "name": "New Year's Day",
                "month": 1,
                "day": 1,
                "type": "national"
            },
            {
                "name": "Workers' Day",
                "month": 5,
                "day": 1,
                "type": "national"
            },
            {
                "name": "Democracy Day",
                "month": 6,
                "day": 12,
                "type": "national"
            },
            {
                "name": "Independence Day",
                "month": 10,
                "day": 1,
                "type": "national"
            },
            {
                "name": "Christmas Day",
                "month": 12,
                "day": 25,
                "type": "holiday"
            }
        ]

        for item in shared_remembers:

            occurrence = next_annual_occurrence(
                item["month"],
                item["day"]
            )

            reminders.append({
                "name": item["name"],
                "date": occurrence,
                "type": item["type"],
                "source": "shared",
                "kind": "shared"
            })


    # =================================
    # REMOVE EXACT DUPLICATES
    # =================================

    unique_reminders = []
    seen = set()

    for reminder in reminders:

        key = (
            reminder["name"],
            reminder["date"],
            reminder["type"]
        )

        if key in seen:
            continue

        seen.add(key)
        unique_reminders.append(reminder)


    # =================================
    # SORT
    # =================================

    unique_reminders.sort(
        key=lambda item: item["date"]
    )

    return unique_reminders


    