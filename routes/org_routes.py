from flask import request, redirect, render_template, session, Blueprint, url_for, flash, current_app
from models import Organization, OrgInvite, OrgSettings, User, Event, MessageTemplate, Question, Department, EventResponse, \
    Remember, Notification
from extensions import db, bcrypt
from datetime import datetime, timedelta, date, timezone
from utils.timezone_utils import to_local_time, get_org
from utils.email_service import create_email_verification
from collections import defaultdict, Counter
from sqlalchemy import func, desc
from werkzeug.utils import secure_filename
from services.remember_service import (
    get_org_upcoming_remembers
)
import secrets
import uuid
import os


# Org Blueprint
org_bp = Blueprint("org", __name__)

# Image config
ALLOWED_LOGO_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "webp"
}

MAX_LOGO_SIZE = 2 * 1024 * 1024  # 2MB


def allowed_logo(filename):
    return (
        filename
        and "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_LOGO_EXTENSIONS
    )


def save_org_logo(file):

    if not file or not file.filename:
        return None

    if not allowed_logo(file.filename):
        return None

    # Read file to enforce size limit
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)

    if file_size > MAX_LOGO_SIZE:
        return None

    extension = secure_filename(
        file.filename
    ).rsplit(".", 1)[1].lower()

    filename = (
        f"{uuid.uuid4().hex}.{extension}"
    )

    upload_folder = os.path.join(
        current_app.static_folder,
        "uploads",
        "org_logos"
    )

    os.makedirs(
        upload_folder,
        exist_ok=True
    )

    file.save(
        os.path.join(
            upload_folder,
            filename
        )
    )

    return f"uploads/org_logos/{filename}"


def delete_org_logo(logo_path):

    if not logo_path:
        return

    full_path = os.path.join(
        current_app.static_folder,
        logo_path
    )

    if os.path.exists(full_path):
        os.remove(full_path)


# ROUTES
# Auth
@org_bp.route("/org/signup", methods=["GET", "POST"])
def org_signup():

    if request.method == "POST":

        org_name = request.form["org_name"].strip()
        email = request.form["email"].strip().lower()
        phone = request.form.get("phone_no", "").strip()

        # =========================
        # 🔍 CHECK DUPLICATE ORG
        # =========================
        existing = Organization.query.filter_by(
            name=org_name
        ).first()

        if existing:
            return "Organization already exists!"

        # =========================
        # 🔍 CHECK DUPLICATE USER
        # =========================
        existing_user = User.query.filter_by(
            email=email
        ).first()

        if existing_user:
            return "An account already exists with this email"

        # =========================
        # 🏢 CREATE ORGANIZATION
        # =========================
        org = Organization(
            name=org_name,
            slug=(
                org_name.lower().replace(" ", "-")
                + "-"
                + str(uuid.uuid4())[:5]
            ),
            location=request.form.get("state"),
            country=request.form.get("country"),
            industry=request.form.get("industry"),
            is_active=True,
            is_verified=False
        )

        db.session.add(org)
        db.session.flush()

        # =========================
        # 👤 CREATE OWNER
        # =========================
        owner = User(
            org_id=org.id,
            first_name=request.form.get("first_name"),
            last_name=request.form.get("last_name"),
            email=email,
            phone=phone,
            password_hash=bcrypt.generate_password_hash(
                request.form["password"]
            ).decode("utf-8"),
            role="owner",
            is_email_verified=False
        )

        db.session.add(owner)
        db.session.commit()

        # =========================
        # 📧 CREATE & SEND OTP
        # =========================
        create_email_verification(owner)

        # =========================
        # 🔐 TEMPORARY VERIFICATION SESSION
        # =========================
        session.clear()

        session["pending_verification_user_id"] = owner.id
        session["pending_verification_type"] = "owner"

        # =========================
        # ➡️ VERIFY EMAIL
        # =========================

        return redirect(
            url_for("user.verify_email")
        )

    return render_template("org_signup.html")


# Auto-detect step from DB
def get_onboarding_step(org):

    if not org.org_type or not org.slogan:
        return 1

    has_departments = Department.query.filter_by(org_id=org.id).first()
    if not has_departments:
        return 2

    if not org.comm_type or not org.timezone:
        return 3

    return "complete"


# Onboarding
@org_bp.route("/org/onboarding/step-1", methods=["GET", "POST"])
def org_onboarding_step_1():

    org_id = session.get("org_id")

    if not org_id:
        return redirect(url_for("user.user_login"))

    org = Organization.query.get(org_id)

    if not org:
        session.clear()
        return redirect(url_for("user.user_login"))

    if request.method == "POST":

        # =========================
        # STEP 1: ORGANIZATION PROFILE
        # =========================
        org.org_type = request.form.get("org_type")
        org.slogan = request.form.get("slogan", "").strip()

        # =========================
        # IMPORTANT DATES
        # =========================
        date_established = request.form.get(
            "date_established",
            ""
        ).strip()

        founders_day = request.form.get(
            "founders_day",
            ""
        ).strip()

        # =========================
        # ORGANIZATION ANNIVERSARY
        # =========================
        if date_established:

            try:
                parsed_date = datetime.strptime(
                    date_established,
                    "%Y-%m-%d"
                ).date()

            except ValueError:
                return render_template(
                    "onboarding/step_1_identity.html",
                    org=org,
                    error="Please enter a valid establishment date."
                )

            existing_remember = Remember.query.filter_by(
                org_id=org.id,
                remember_type="organization_anniversary"
            ).first()

            if existing_remember:

                existing_remember.date = parsed_date
                existing_remember.name = "Organization Anniversary"
                existing_remember.is_recurring = True
                existing_remember.is_active = True

            else:

                remember = Remember(
                    org_id=org.id,
                    name="Organization Anniversary",
                    date=parsed_date,
                    remember_type="organization_anniversary",
                    is_recurring=True,
                    is_active=True
                )

                db.session.add(remember)

        # =========================
        # FOUNDER'S DAY
        # =========================
        if founders_day:

            try:
                parsed_founders_day = datetime.strptime(
                    founders_day,
                    "%Y-%m-%d"
                ).date()

            except ValueError:
                return render_template(
                    "onboarding/step_1_identity.html",
                    org=org,
                    error="Please enter a valid Founder's Day."
                )

            existing_remember = Remember.query.filter_by(
                org_id=org.id,
                remember_type="founders_day"
            ).first()

            if existing_remember:

                existing_remember.date = parsed_founders_day
                existing_remember.name = "Founder's Day"
                existing_remember.is_recurring = True
                existing_remember.is_active = True

            else:

                remember = Remember(
                    org_id=org.id,
                    name="Founder's Day",
                    date=parsed_founders_day,
                    remember_type="founders_day",
                    is_recurring=True,
                    is_active=True
                )

                db.session.add(remember)

        # =========================
        # ORGANIZATION LOGO
        # =========================

        remove_logo = request.form.get(
            "remove_logo"
        ) == "1"

        logo_file = request.files.get("logo")

        if remove_logo:

            if org.logo:
                delete_org_logo(org.logo)

            org.logo = None

        elif logo_file and logo_file.filename:

            new_logo = save_org_logo(logo_file)

            if not new_logo:
                flash(
                    "Please upload a valid logo "
                    "(PNG, JPG, JPEG or WEBP, max 2MB).",
                    "error"
                )

                return redirect(
                    url_for("org.org_settings")
                )

            if org.logo:
                delete_org_logo(org.logo)

            org.logo = new_logo

        # =========================
        # SAVE EVERYTHING
        # =========================
        db.session.commit()

        # =========================
        # MARK PROGRESS
        # =========================
        session["onboarding_step"] = 2

        return redirect(
            url_for("org.org_onboarding_step_2")
        )

    return render_template(
        "onboarding/step_1_identity.html",
        org=org
    )


@org_bp.route("/org/onboarding/step-2", methods=["GET", "POST"])
def org_onboarding_step_2():

    org_id = session.get("org_id")

    if not org_id:
        return redirect(url_for("org.org_login"))

    org = Organization.query.get(org_id)

    if request.method == "POST":

        # =========================
        # STRUCTURE: DEPARTMENTS
        # =========================
        raw_departments = request.form.get("departments")

        if raw_departments:

            dept_list = [
                d.strip()
                for d in raw_departments.split(",")
                if d.strip()
            ]

            for name in dept_list:

                exists = Department.query.filter_by(
                    org_id=org.id,
                    name=name
                ).first()

                if not exists:
                    dept = Department(
                        org_id=org.id,
                        name=name
                    )
                    db.session.add(dept)

        db.session.commit()

        session["onboarding_step"] = 3

        return redirect(url_for("org.org_onboarding_step_3"))

    # load existing departments for preview
    departments = Department.query.filter_by(org_id=org.id).all()

    return render_template(
        "onboarding/step_2_structure.html",
        org=org,
        departments=departments
    )



@org_bp.route("/org/onboarding/step-3", methods=["GET", "POST"])
def org_onboarding_step_3():

    org_id = session.get("org_id")

    if not org_id:
        return redirect(
            url_for("org.org_login")
        )

    org = Organization.query.get(org_id)

    if not org:
        session.clear()

        return redirect(
            url_for("org.org_login")
        )

    # =========================
    # LOAD OR CREATE SETTINGS
    # =========================

    settings = OrgSettings.query.filter_by(
        org_id=org.id
    ).first()

    if not settings:

        settings = OrgSettings(
            org_id=org.id
        )

        db.session.add(settings)

    # =========================
    # SAVE PREFERENCES
    # =========================

    if request.method == "POST":

        settings.comm_type = request.form.get(
            "comm_type",
            "email"
        )

        settings.timezone = request.form.get(
            "timezone",
            "Africa/Lagos"
        )

        # Keep Organization timezone synchronized.
        org.timezone = settings.timezone

        # ---------------------------------
        # MARK ORGANIZATION ONBOARDING DONE
        # ---------------------------------

        org.onboarding_completed = True

        # ---------------------------------
        # MARK OWNER ONBOARDING DONE
        # ---------------------------------

        user_id = session.get("user_id")

        if user_id:

            user = User.query.filter_by(
                id=user_id,
                org_id=org.id,
                role="owner"
            ).first()

            if user:

                user.is_onboarded = True

                user.onboarding_completed_at = (
                    datetime.now(timezone.utc)
                )

        db.session.commit()

        session["onboarding_step"] = "complete"

        return redirect(
            url_for("org.org_onboarding_complete")
        )

    return render_template(
        "onboarding/step_3_preferences.html",
        org=org,
        settings=settings
    )


@org_bp.route("/org/onboarding/complete")
def org_onboarding_complete():

    org_id = session.get("org_id")

    if not org_id:
        return redirect(
            url_for("org.org_login")
        )

    return render_template(
        "onboarding/complete.html"
    )



@org_bp.route("/org/onboarding", methods=["GET", "POST"])
def org_onboarding():

    org_id = session.get("org_id")

    if not org_id:
        return redirect(url_for("org.org_login"))

    org = Organization.query.get(org_id)

    if request.method == "POST":

        # =========================
        # IDENTITY FIELDS
        # =========================
        org.org_type = request.form.get("org_type")
        org.slogan = request.form.get("bio")

        # =========================
        # STRUCTURE (DEPARTMENTS)
        # =========================
        raw_departments = request.form.get("departments_preview") or ""

        dept_list = [
            d.strip().title()
            for d in raw_departments.split(",")
            if d.strip()
        ]

        # preload existing names (OPTIMIZED)
        existing = {
            d.name.lower()
            for d in Department.query.filter_by(org_id=org.id).all()
        }

        for name in dept_list:

            if name.lower() in existing:
                continue

            db.session.add(
                Department(
                    org_id=org.id,
                    name=name
                )
            )

        db.session.commit()

        return redirect(url_for("org.org_dashboard"))

    return render_template("org_onboarding.html", org=org)


# =================================
# ORGANIZATION DASHBOARD
# =================================
@org_bp.route("/org/dashboard")
def org_dashboard():

    # =========================
    # 🔐 AUTH CHECK
    # =========================
    user_id = session.get("user_id")

    if not user_id:
        return redirect(
            url_for("user.user_login")
        )

    # =========================
    # 👤 LOAD USER
    # =========================
    user = User.query.get(user_id)

    if not user:
        session.clear()

        return redirect(
            url_for("user.user_login")
        )

    # =========================
    # 🔑 OWNER ACCESS ONLY
    # =========================
    if user.role != "owner":
        return "Access Denied", 403

    # =========================
    # 🏢 LOAD ORGANIZATION
    # =========================
    org = Organization.query.get(
        user.org_id
    )

    if not org:
        return "Organization not found", 404

    if not org.is_active:
        return "Organization is not active", 403

    # =========================
    # 🧭 ONBOARDING CHECK
    # =========================
    if not org.org_type:
        return redirect(
            url_for("org.org_onboarding_step_1")
        )


    # =========================
    # 🧠 UPCOMING REMEMBERS
    # =========================

    all_upcoming_remembers = get_org_upcoming_remembers(
        org=org
    )

    remember_count = len(all_upcoming_remembers)

    # Dashboard displays only the next 5
    upcoming_remembers = all_upcoming_remembers[:5]

    # =========================
    # 👥 MEMBER COUNT
    # =========================
    member_count = User.query.filter_by(
        org_id=org.id
    ).count()

    # =========================
    # 🔗 ACTIVE INVITE
    # =========================
    invite = OrgInvite.query.filter_by(
        org_id=org.id,
        is_active=True
    ).first()

    invite_link = None

    if invite:
        invite_link = (
            request.host_url
            + "signup/"
            + invite.invite_code
        )

    # =========================
    # 📊 TOTAL EVENTS
    # =========================
    tot_event = Event.query.filter_by(
        org_id=org.id
    ).count()

    # =========================
    # 💚 ACTIVE CHECK-IN EVENT
    # =========================
    event = Event.query.filter_by(
        org_id=org.id,
        event_type="checkin",
        is_active=True
    ).first()

    # Default values
    total_responses = 0
    today_responses = 0
    trend_labels = []
    trend_values = []

    # =========================
    # 📈 CHECK-IN ANALYTICS
    # =========================
    if event:

        # Total responses
        total_responses = EventResponse.query.filter_by(
            event_id=event.id
        ).count()

        # Today's responses
        today_responses = EventResponse.query.filter_by(
            event_id=event.id,
            submitted_for_date=date.today()
        ).count()

        # Last 7 days
        start_date = date.today() - timedelta(days=6)

        raw = db.session.query(
            EventResponse.submitted_for_date,
            func.count(EventResponse.id)
        ).filter(
            EventResponse.event_id == event.id,
            EventResponse.submitted_for_date >= start_date
        ).group_by(
            EventResponse.submitted_for_date
        ).all()

        trend_map = {
            r[0]: r[1]
            for r in raw
        }

        for i in range(7):

            day = start_date + timedelta(days=i)

            trend_labels.append(
                day.strftime("%a")
            )

            trend_values.append(
                trend_map.get(day, 0)
            )

    # =========================
    # 🕒 RECENT ACTIVITY
    # =========================
    recent_activity = []

    latest_checkins = (
        EventResponse.query
        .join(User)
        .join(Event)
        .filter(
            Event.org_id == org.id
        )
        .order_by(
            desc(EventResponse.created_at)
        )
        .limit(5)
        .all()
    )

    for response in latest_checkins:

        event_name = (
            response.event.name
            if response.event
            else "Wellbeing Check-in"
        )

        # Use timezone-aware datetime consistently
        created_at = response.created_at

        if created_at.tzinfo is None:
            created_at = created_at.replace(
                tzinfo=timezone.utc
            )

        diff = (
            datetime.now(timezone.utc)
            - created_at
        )

        if diff.days > 0:

            time_ago = (
                f"{diff.days} day"
                f"{'s' if diff.days > 1 else ''} ago"
            )

        elif diff.seconds >= 3600:

            hours = diff.seconds // 3600

            time_ago = (
                f"{hours} hour"
                f"{'s' if hours > 1 else ''} ago"
            )

        else:

            mins = max(
                1,
                diff.seconds // 60
            )

            time_ago = (
                f"{mins} minute"
                f"{'s' if mins > 1 else ''} ago"
            )

        recent_activity.append({
            "user_name": response.user.first_name,

            "profile_image": getattr(
                response.user,
                "profile_pic",
                None
            ),

            "activity": "checked in",

            "time_ago": time_ago,

            "event_name": event_name
        })

    print(f"remembers => {upcoming_remembers}")

    # =========================
    # 🖥️ DASHBOARD
    # =========================
    return render_template(
        "org/org_dashboard.html",

        user=user,
        org=org,

        event=event,

        invite=invite,
        invite_link=invite_link,

        member_count=member_count,

        tot_event=tot_event,

        total_responses=total_responses,
        today_responses=today_responses,

        trend_labels=trend_labels,
        trend_values=trend_values,

        recent_activity=recent_activity,

        # Remember
        upcoming_remembers=upcoming_remembers,
        remember_count=remember_count
    )



# Invites
@org_bp.route("/org/invite", methods=["GET", "POST"])
def generate_invite():

    user_id = session.get("user_id")

    if not user_id:
        return redirect("/login")

    user = User.query.get(user_id)
    # 🏢 get org
    org = Organization.query.get(user.org_id)

    if not user or user.role != "owner":
        return "Unauthorized"

    # 🔁 Check if active invite already exists
    invite = OrgInvite.query.filter_by(
        org_id=user.org_id,
        is_active=True
    ).first()

    # 🆕 Create new if none
    if not invite:
        invite = OrgInvite(
            org_id=user.org_id,
            invite_code=secrets.token_urlsafe(8),
            expires_at=datetime.utcnow() + timedelta(days=1)  # optional expiry
        )
        db.session.add(invite)
        db.session.commit()

        session['invite_id'] = invite.id

    # 🔗 Build full link
    invite_link = request.host_url + "signup/" + invite.invite_code
    member_count = User.query.filter_by(org_id=org.id).count()

    return render_template(
        "org_invite.html",
        invite_link=invite_link,
        org=org,
        invite=invite,
        created_at=invite.created_at,
        expires_at=invite.expires_at,
        is_active=invite.is_active,
        member_count=member_count
    )


@org_bp.route("/org/invite/regenerate")
def regenerate_invite():

    user = User.query.get(session["user_id"])

    # deactivate old
    OrgInvite.query.filter_by(
        org_id=user.org_id
    ).update({"is_active": False})

    new_invite = OrgInvite(
        org_id=user.org_id,
        invite_code=secrets.token_urlsafe(8)
    )

    db.session.add(new_invite)
    db.session.commit()
 
    return redirect("/org/invite")



# =================================
# REMEMBERS
# =================================
@org_bp.route("/org/remembers")
def org_remembers():

    # =========================
    # 🔐 AUTH CHECK
    # =========================
    user_id = session.get("user_id")

    if not user_id:
        flash(
            "Please log in to continue.",
            "error"
        )

        return redirect(
            url_for("org.org_login")
        )

    # =========================
    # 👤 LOAD USER
    # =========================
    user = User.query.get(user_id)

    if not user:
        session.clear()

        flash(
            "Your session could not be verified. Please log in again.",
            "error"
        )

        return redirect(
            url_for("org.org_login")
        )

    # =========================
    # 🔑 OWNER ACCESS ONLY
    # =========================
    if user.role != "owner":

        flash(
            "You do not have permission to access organization Remembers.",
            "error"
        )

        return redirect(
            url_for("user.user_dashboard")
        )

    # =========================
    # 🏢 LOAD ORGANIZATION
    # =========================
    org = Organization.query.get(
        user.org_id
    )

    if not org:

        flash(
            "Your organization could not be found.",
            "error"
        )

        return redirect(
            url_for("org.org_login")
        )

    if not org.is_active:

        flash(
            "Your organization is currently inactive.",
            "error"
        )

        return redirect(
            url_for("org.org_login")
        )

    # =========================
    # 🧭 ONBOARDING
    # =========================
    if not org.org_type:

        flash(
            "Please complete your organization setup first.",
            "info"
        )

        return redirect(
            url_for("org.org_onboarding_step_1")
        )

    # =========================
    # 🧠 UNIFIED REMEMBERS
    # =========================
    all_remembers = get_org_upcoming_remembers(
        org=org
    )

    # =========================
    # 📊 SUMMARY COUNTS
    # =========================
    organization_count = Remember.query.filter_by(
        org_id=org.id
    ).count()

    member_count = sum(
        1
        for item in all_remembers
        if item.get("source") == "member"
    )

    shared_count = sum(
        1
        for item in all_remembers
        if item.get("source") == "shared"
    )

    # =========================
    # 🔎 FILTERS
    # =========================
    source_filter = request.args.get(
        "source",
        "all"
    )

    type_filter = request.args.get(
        "type",
        "all"
    )

    filtered_remembers = all_remembers

    if source_filter != "all":

        filtered_remembers = [
            item
            for item in filtered_remembers
            if item.get("source") == source_filter
        ]

    if type_filter != "all":

        filtered_remembers = [
            item
            for item in filtered_remembers
            if item.get("type") == type_filter
        ]

    # =========================
    # 📄 PAGINATION
    # =========================
    page = request.args.get(
        "page",
        1,
        type=int
    )

    per_page = 10

    total_items = len(filtered_remembers)

    total_pages = max(
        1,
        (total_items + per_page - 1)
        // per_page
    )

    if page < 1:
        page = 1

    if page > total_pages:
        page = total_pages

    start = (
        page - 1
    ) * per_page

    end = start + per_page

    paginated_remembers = filtered_remembers[
        start:end
    ]

    # =========================
    # 🖥️ PAGE
    # =========================
    return render_template(
        "org/org_remembers.html",

        org=org,

        # Unified list
        remembers=paginated_remembers,

        # Summary
        organization_count=organization_count,
        member_count=member_count,
        shared_count=shared_count,

        # Filtering
        source_filter=source_filter,
        type_filter=type_filter,

        # Pagination
        page=page,
        total_pages=total_pages,
        total_items=total_items,
        per_page=per_page,

        has_prev=page > 1,
        has_next=page < total_pages,

        prev_page=page - 1,
        next_page=page + 1
    )



@org_bp.route("/org/remembers/add", methods=["POST"])
def add_remember():

    org_id = session.get("org_id")

    if not org_id:
        return redirect(url_for("org.org_login"))

    org = Organization.query.get(org_id)

    if not org:
        session.clear()
        return redirect(url_for("org.org_login"))

    # =========================
    # FORM DATA
    # =========================
    name = request.form.get("name", "").strip()
    date_value = request.form.get("date", "").strip()
    remember_type = request.form.get("remember_type", "").strip()
    is_recurring = request.form.get("is_recurring") == "1"

    # =========================
    # VALIDATION
    # =========================
    if not name:
        flash("Remember name is required.", "error")
        return redirect(url_for("org.org_remembers"))

    if not date_value:
        flash("Date is required.", "error")
        return redirect(url_for("org.org_remembers"))

    if not remember_type:
        flash("Remember type is required.", "error")
        return redirect(url_for("org.org_remembers"))

    try:
        parsed_date = datetime.strptime(
            date_value,
            "%Y-%m-%d"
        ).date()

    except ValueError:
        flash("Please enter a valid date.", "error")
        return redirect(url_for("org.org_remembers"))

    # =========================
    # CREATE REMEMBER
    # =========================
    remember = Remember(
        org_id=org.id,
        name=name,
        date=parsed_date,
        remember_type=remember_type,
        is_recurring=is_recurring,
        is_active=True
    )

    db.session.add(remember)
    db.session.commit()

    flash("Remember added successfully.", "success")

    return redirect(
        url_for("org.org_remembers")
    )



# =================================
# EDIT ORGANIZATION REMEMBER
# =================================

@org_bp.route("/org/remembers/<int:remember_id>/edit",methods=["POST"])
def edit_remember(remember_id):

    org_id = session.get("org_id")

    if not org_id:
        return redirect(
            url_for("org.org_login")
        )

    remember = Remember.query.filter_by(
        id=remember_id,
        org_id=org_id,
        is_active=True
    ).first_or_404()

    # =========================
    # FORM DATA
    # =========================

    name = request.form.get(
        "name",
        ""
    ).strip()

    date_value = request.form.get(
        "date",
        ""
    ).strip()

    remember_type = request.form.get(
        "remember_type",
        ""
    ).strip()

    is_recurring = (
        request.form.get("is_recurring") == "1"
    )

    # =========================
    # VALIDATION
    # =========================

    if not name:

        flash(
            "Remember name is required.",
            "error"
        )

        return redirect(
            url_for("org.org_remembers")
        )

    if not date_value:

        flash(
            "Date is required.",
            "error"
        )

        return redirect(
            url_for("org.org_remembers")
        )

    if not remember_type:

        flash(
            "Remember type is required.",
            "error"
        )

        return redirect(
            url_for("org.org_remembers")
        )

    try:

        parsed_date = datetime.strptime(
            date_value,
            "%Y-%m-%d"
        ).date()

    except ValueError:

        flash(
            "Please enter a valid date.",
            "error"
        )

        return redirect(
            url_for("org.org_remembers")
        )

    # =========================
    # UPDATE
    # =========================

    remember.name = name
    remember.date = parsed_date
    remember.remember_type = remember_type
    remember.is_recurring = is_recurring

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        flash(
            "We couldn't update the Remember. Please try again.",
            "error"
        )

        return redirect(
            url_for("org.org_remembers")
        )

    flash(
        "Remember updated successfully.",
        "success"
    )

    return redirect(
        url_for("org.org_remembers")
    )



# =================================
# DELETE ORGANIZATION REMEMBER
# =================================

@org_bp.route("/org/remembers/<int:remember_id>/delete", methods=["POST"])
def delete_remember(remember_id):

    org_id = session.get("org_id")

    if not org_id:
        return redirect(
            url_for("org.org_login")
        )

    remember = Remember.query.filter_by(
        id=remember_id,
        org_id=org_id,
        is_active=True
    ).first_or_404()

    remember.is_active = False

    db.session.commit()

    flash(
        "Remember deleted successfully.",
        "success"
    )

    return redirect(
        url_for("org.org_remembers")
    )


# Org Settings
@org_bp.route("/org/settings", methods=["GET", "POST"])
def org_settings():

    # =========================
    # AUTH CHECK
    # =========================
    user_id = session.get("user_id")

    if not user_id:
        return redirect(url_for("org.org_login"))

    # =========================
    # LOAD USER
    # =========================
    user = User.query.get(user_id)

    if not user:
        session.clear()
        return redirect(url_for("org.org_login"))

    # =========================
    # OWNER / ADMIN ONLY
    # =========================
    if user.role not in ["owner", "admin"]:
        return "Access Denied", 403

    # =========================
    # LOAD ORGANIZATION
    # =========================
    org = Organization.query.get(user.org_id)

    if not org:
        return "Organization not found", 404

    if not org.is_active:
        return "Organization is not active", 403

    # =========================
    # LOAD OR CREATE SETTINGS
    # =========================
    settings = OrgSettings.query.filter_by(
        org_id=org.id
    ).first()

    if not settings:
        settings = OrgSettings(
            org_id=org.id
        )

        db.session.add(settings)
        db.session.commit()

    # =========================
    # SAVE SETTINGS
    # =========================
    if request.method == "POST":

        # =================================
        # ORGANIZATION PROFILE
        # =================================
        org.name = request.form.get(
            "name",
            org.name
        ).strip()

        org.org_type = request.form.get(
            "org_type"
        )

        org.industry = request.form.get(
            "industry"
        )

        org.location = request.form.get(
            "location"
        )

        org.slogan = request.form.get(
            "slogan",
            ""
        ).strip()

        # =================================
        # ORGANIZATION LOGO
        # =================================

        remove_logo = request.form.get(
            "remove_logo"
        ) == "1"

        logo_file = request.files.get("logo")

        # Remove current logo
        if remove_logo:

            if org.logo:
                delete_org_logo(org.logo)

            org.logo = None

        # Replace / add logo
        elif logo_file and logo_file.filename:

            new_logo = save_org_logo(
                logo_file
            )

            if not new_logo:

                flash(
                    "Please upload a valid logo "
                    "(PNG, JPG, JPEG or WEBP, max 2MB).",
                    "error"
                )

                return redirect(
                    url_for("org.org_settings")
                )

            # Delete old logo after successfully
            # saving the new one
            if org.logo:
                delete_org_logo(org.logo)

            org.logo = new_logo

        # =================================
        # ORGANIZATION PREFERENCES
        # =================================
        settings.comm_type = request.form.get(
            "comm_type"
        )

        settings.timezone = request.form.get(
            "timezone"
        )

        settings.default_view = request.form.get(
            "default_view"
        )

        settings.checkin_frequency = request.form.get(
            "checkin_frequency"
        )

        settings.reminder_enabled = (
            request.form.get(
                "reminder_enabled"
            ) == "1"
        )

        settings.allow_self_join = (
            request.form.get(
                "allow_self_join"
            ) == "1"
        )

        settings.require_approval = (
            request.form.get(
                "require_approval"
            ) == "1"
        )

        # =================================
        # KEEP TIMEZONE SYNCHRONIZED
        # =================================
        org.timezone = settings.timezone

        # =================================
        # SAVE EVERYTHING
        # =================================
        db.session.commit()

        flash(
            "Organization settings updated successfully.",
            "success"
        )

        return redirect(
            url_for("org.org_settings")
        )

    return render_template(
        "org/org_settings.html",
        org=org,
        settings=settings,
        user=user
    )

# Events
@org_bp.route("/org/events")
def events_dashboard():

    org_id = session.get("org_id")

    if not org_id:
        return redirect(url_for("org.org_login"))

    events = Event.query.filter_by(org_id=org_id).all()

    total_events = len(events)
    active_events = len([e for e in events if e.is_active])

    event_metrics = {}

    today = datetime.utcnow().date()

    for event in events:

        # total responses for this event
        total_responses = EventResponse.query.filter_by(event_id=event.id).count()

        # today's responses
        today_responses = EventResponse.query.filter(
            EventResponse.event_id == event.id,
            func.date(EventResponse.created_at) == today
        ).count()

        event_metrics[event.id] = {
            "total_responses": total_responses,
            "today_responses": today_responses
        }

    return render_template(
        "org/events_dashboard.html",
        events=events,
        total_events=total_events,
        active_events=active_events,
        event_metrics=event_metrics
    )


@org_bp.route("/org/events/<int:event_id>")
def event_details(event_id):

    org_id = session.get("org_id")
    if not org_id:
        return redirect(url_for("org.org_login"))

    event = Event.query.filter_by(id=event_id, org_id=org_id).first()

    if not event:
        return "Event not found", 404

    # all responses
    responses = EventResponse.query.filter_by(event_id=event.id).all()

    today = datetime.utcnow().date()

    total_responses = len(responses)

    today_responses = EventResponse.query.filter(
        EventResponse.event_id == event.id,
        func.date(EventResponse.created_at) == today
    ).count()

    # -------------------------
    # MOOD ANALYTICS (Q1 assumed)
    # -------------------------
    mood_counts = {1:0, 2:0, 3:0, 4:0, 5:0}

    for r in responses:
        if r.question.question_type == "mood":
            try:
                mood_counts[int(r.answer)] += 1
            except:
                pass

    mood_labels = ["Struggling", "Low", "Okay", "Good", "Great"]
    mood_values = list(mood_counts.values())

    # -------------------------
    # SUPPORT BREAKDOWN (Q4)
    # -------------------------
    support_counts = {}

    for r in responses:
        if r.question.question_key == "support_details" and r.answer:
            support_counts[r.answer] = support_counts.get(r.answer, 0) + 1

    support_labels = list(support_counts.keys())
    support_values = list(support_counts.values())

    # -------------------------
    # RECENT RESPONSES
    # -------------------------
    recent = (
        EventResponse.query
        .filter_by(event_id=event.id)
        .order_by(EventResponse.created_at.desc())
        .limit(5)
        .all()
    )

    return render_template(
        "org/event_details.html",
        event=event,
        total_responses=total_responses,
        today_responses=today_responses,
        mood_labels=mood_labels,
        mood_values=mood_values,
        support_labels=support_labels,
        support_values=support_values,
        recent=recent
    )


@org_bp.route("/org/events/create", methods=["GET", "POST"])
def create_event():

    org_id = session.get("org_id")

    if not org_id:
        return redirect(url_for("org.org_login"))

    org = Organization.query.get(org_id)

    if not org:
        return "Organization not found", 404

    if not org.org_type:
        return redirect(url_for("org.org_onboarding"))

    if request.method == "POST":

        try:
            # =========================
            # BASIC EVENT DATA
            # =========================
            title = request.form.get("title")
            event_type = request.form.get("event_type")

            if not title or not event_type:
                return "Title and event type are required", 400

            event = Event(
                org_id=org_id,
                name=title,  # ✅ FIXED (was title → now name)
                event_type=event_type,
                #description=request.form.get("description"),

                # trigger defaults
                trigger_type=request.form.get("trigger_type") or "date",
                frequency=request.form.get("frequency") or "weekly",

                # audience
                audience_type=request.form.get("audience_type") or "all",

                is_active=True
            )

            # Optional trigger date
            trigger_date = request.form.get("trigger_date")
            if trigger_date:
                event.trigger_date = datetime.strptime(trigger_date, "%Y-%m-%d").date()

            print(f"Event create deets => {event}")

            db.session.add(event)
            db.session.flush()  # get event.id

            # =========================
            # QUESTIONS (max 5)
            # =========================
            questions = [
                q.strip()
                for q in request.form.getlist("questions")
                if q.strip()
            ][:5]

            for q_text in questions:
                question = Question(
                    org_id=org_id,
                    event_id=event.id,
                    question_text=q_text
                )
                db.session.add(question)

            # =========================
            # MESSAGE TEMPLATE
            # =========================
            template = MessageTemplate(
                org_id=org_id,
                event_id=event.id,
                subject=request.form.get("subject"),
                body_template=request.form.get("body"),
                channel=request.form.get("channel")
            )

            db.session.add(template)

            # =========================
            # COMMIT ALL
            # =========================
            db.session.commit()

            saved_event = Event.query.get(event.id)

            print("SAVED EVENT =>", {
                "id": saved_event.id,
                "name": saved_event.name,
                "trigger_type": saved_event.trigger_type,
                "frequency": saved_event.frequency,
                "event_type": saved_event.event_type
            })

            return redirect(url_for("org.events_dashboard"))

        except Exception as e:
            db.session.rollback()
            return f"Error creating event: {str(e)}"

    return render_template("org/create_event.html")


@org_bp.route("/org/events/delete/<int:event_id>", methods=["POST"])
def delete_event(event_id):

    org_id = session.get("org_id")
    if not org_id:
        return redirect(url_for("org.org_login"))

    # ensure event belongs to org
    event = Event.query.filter_by(id=event_id, org_id=org_id).first()

    if not event:
        return "Event not found or unauthorized", 404

    db.session.delete(event)
    db.session.commit()

    return redirect(url_for("org.events_dashboard"))


@org_bp.route("/org/events/<int:event_id>/update", methods=["POST"])
def update_event(event_id):

    org_id = session.get("org_id")
    if not org_id:
        return redirect(url_for("org.org_login"))

    event = Event.query.filter_by(id=event_id, org_id=org_id).first()

    if not event:
        return "Event not found", 404

    event.name = request.form.get("name")
    event.frequency = request.form.get("frequency")
    event.audience_type = request.form.get("audience_type")

    db.session.commit()

    return redirect(url_for("org.events_dashboard"))


@org_bp.route("/org/events/<int:event_id>/toggle", methods=["POST"])
def toggle_event(event_id):

    org_id = session.get("org_id")
    if not org_id:
        return {"error": "unauthorized"}, 403

    event = Event.query.filter_by(id=event_id, org_id=org_id).first()

    if not event:
        return {"error": "not found"}, 404

    event.is_active = not event.is_active
    db.session.commit()

    return {
        "success": True,
        "is_active": event.is_active
    }


@org_bp.route("/org/checkin-overview")
def org_checkin_overview():
    org_id = session.get("org_id")

    # 🏢 get org
    #org = Organization.query.get(org_id)
    org = Organization.query.get(session["org_id"])
    
    if not org_id:
        return redirect("/login")

    # Security: Only allow owners
    if session.get("role") != "owner":
        return "Access Denied", 403

    page = request.args.get('page', 1, type=int)
    per_page = 12   # You can change this

    event = Event.query.filter_by(org_id=org_id, event_type="checkin").first()
    # convrt to localtime
    event.created_at = to_local_time(event.created_at, org.timezone)
    if not event:
        return render_template("org/checkin_overview.html", checkins={}, pagination=None, event=None)

    # Fetch responses with pagination
    responses = EventResponse.query.join(User)\
        .filter(EventResponse.event_id == event.id)\
        .order_by(EventResponse.submitted_for_date.desc(), EventResponse.created_at.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)

    from collections import defaultdict
    checkins = defaultdict(lambda: defaultdict(dict))

    for r in responses.items:
        date_key = r.submitted_for_date.strftime("%Y-%m-%d")
        display_date = r.submitted_for_date.strftime("%A, %B %d, %Y")
        time_str = r.created_at.strftime("%I:%M %p") if r.created_at else ""

        user_key = r.user_id

        if user_key not in checkins[date_key]:
            checkins[date_key][user_key] = {
                'user': r.user,
                'display_date': display_date,
                'time': time_str,
                'answers': {}
            }

        checkins[date_key][user_key]['answers'][r.question.question_text] = r.answer

    return render_template("org/checkin_overview.html", 
                           checkins=checkins,
                           pagination=responses,
                           event=event)


@org_bp.route("/org/analytics")
def org_analytics():
    org_id = session.get("org_id")
    org = get_org()
    
    if not org_id:
        return redirect("/login")

    if session.get("role") != "owner":
        return "Access Denied", 403

    event = Event.query.filter_by(
        org_id=org_id,
        event_type="checkin"
    ).first()

    # convert to local time 
    event.created_at = to_local_time(event.created_at, org.timezone)

    if not event:
        return render_template("org/analytics.html", event=None)

    responses = EventResponse.query.filter_by(event_id=event.id).all()
    print(f"All Event responses => {responses}")

    # =========================
    # 1. MOOD DISTRIBUTION
    # =========================
    mood_counts = Counter()
    
    for r in responses:
        print(f"all users responses::: {r.answer}")
        if r.question.question_type == "mood":
            mood_counts[int(r.answer)] += 1

    mood_labels = ["Strugling", "Down", "Okay", "Good", "Great"]
    mood_values = [mood_counts.get(i, 0) for i in range(1, 6)]

    # =========================
    # 2. SUPPORT NEEDS (Q4)
    # =========================
    support_counts = Counter()

    for r in responses:
        if r.question.question_key == "support_details" and r.answer:
            # checkbox list stored as string OR list
            if isinstance(r.answer, list):
                for a in r.answer:
                    support_counts[a] += 1
            else:
                # fallback if stored as string
                for a in str(r.answer).split(","):
                    support_counts[a.strip()] += 1

    support_labels = list(support_counts.keys())
    support_values = list(support_counts.values())

    # =========================
    # 3. MOOD INSIGHT (simple avg score)
    # =========================
    mood_scores = [
        int(r.answer)
        for r in responses
        if r.question.question_type == "mood" and r.answer
    ]

    mood_avg = round(sum(mood_scores) / len(mood_scores), 2) if mood_scores else 0

    # =========================
    # 4. ENGAGEMENT TREND (7 DAYS)
    # =========================
    today = date.today()
    trend_labels = []
    trend_values = []

    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        count = sum(
            1 for r in responses
            if r.submitted_for_date == d
        )
        trend_labels.append(d.strftime("%a"))
        trend_values.append(count)

    return render_template(
        "org/analytics.html",
        event=event,
        mood_labels=mood_labels,
        mood_values=mood_values,
        support_labels=support_labels,
        support_values=support_values,
        mood_avg=mood_avg,
        trend_labels=trend_labels,
        trend_values=trend_values
    )


@org_bp.route("/org/run-birthday-job")
def run_birthday_job():
    org_id = session.get("org_id")

    from services.birthday_service import process_birthday_events

    result = process_birthday_events(org_id)

    return {
        "status": "success",
        "triggered_count": len(result),
        "details": result
    }



# =================================
# ORGANIZATION NOTIFICATIONS
# =================================

@org_bp.route("/org/notifications")
def org_notifications():

    user_id = session.get("user_id")

    if not user_id:
        flash(
            "Please log in to continue.",
            "error"
        )
        return redirect(
            url_for("user.user_login")
        )

    user = User.query.get(user_id)

    if not user:
        session.clear()

        flash(
            "Your session could not be verified. Please log in again.",
            "error"
        )

        return redirect(
            url_for("user.user_login")
        )

    # ---------------------------------
    # ORGANIZATION ACCESS
    # ---------------------------------

    if user.role not in ["owner", "admin"]:

        flash(
            "You do not have permission to view organization notifications.",
            "error"
        )

        return redirect(
            url_for("user.user_dashboard")
        )

    # ---------------------------------
    # EMAIL VERIFICATION
    # ---------------------------------

    if not user.is_email_verified:

        session.clear()

        session["pending_verification_user_id"] = user.id

        return redirect(
            url_for("user.verify_email")
        )

    # ---------------------------------
    # ORGANIZATION
    # ---------------------------------

    org = Organization.query.get(
        user.org_id
    )

    if not org:

        flash(
            "Your organization could not be found.",
            "error"
        )

        return redirect(
            url_for("user.user_login")
        )

    if not org.is_active:

        flash(
            "Your organization is currently inactive.",
            "error"
        )

        return redirect(
            url_for("user.user_login")
        )

    # ---------------------------------
    # ORGANIZATION NOTIFICATIONS
    # ---------------------------------

    notifications = (
        Notification.query
        .filter_by(
            user_id=user.id,
            org_id=org.id,
            context="organization"
        )
        .order_by(
            Notification.created_at.desc()
        )
        .all()
    )

    unread_count = sum(
        1
        for notification in notifications
        if not notification.is_read
    )

    return render_template(
        "org/org_notifications.html",
        user=user,
        org=org,
        notifications=notifications,
        unread_count=unread_count
    )


# =================================
# MARK ORGANIZATION NOTIFICATION AS READ
# =================================
@org_bp.route("/org/notifications/<int:notification_id>/read",methods=["POST"])
def mark_org_notification_read(notification_id):

    user_id = session.get("user_id")

    if not user_id:
        flash(
            "Please log in to continue.",
            "error"
        )
        return redirect(
            url_for("user.user_login")
        )

    user = User.query.get(user_id)

    if not user:
        session.clear()

        flash(
            "Your session could not be verified. Please log in again.",
            "error"
        )

        return redirect(
            url_for("user.user_login")
        )

    if user.role not in ["owner", "admin"]:
        flash(
            "You do not have permission to view this notification.",
            "error"
        )

        return redirect(
            url_for("user.user_dashboard")
        )

    org = Organization.query.get(user.org_id)

    if not org:
        flash(
            "Your organization could not be found.",
            "error"
        )

        return redirect(
            url_for("user.user_login")
        )

    notification = Notification.query.filter_by(
        id=notification_id,
        user_id=user.id,
        org_id=org.id,
        context="organization"
    ).first()

    if not notification:
        flash(
            "Notification could not be found.",
            "error"
        )

        return redirect(
            url_for("org.org_notifications")
        )

    if not notification.is_read:

        notification.is_read = True
        notification.read_at = datetime.now(timezone.utc)

        db.session.commit()

    if notification.related_url:
        return redirect(notification.related_url)

    return redirect(
        url_for("org.org_notifications")
    )

