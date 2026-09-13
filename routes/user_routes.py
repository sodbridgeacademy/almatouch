from flask import request, redirect, render_template, session, Blueprint, url_for, flash, current_app
from flask import request, redirect, render_template
from flask_login import login_required, current_user
from models import User, UserSettings, UserDepartment, UserRemember, Organization, OrgInvite, Department, UserDepartment, EventResponse, \
    EmailVerification, Notification
from services.event_service import (get_active_checkin_events, get_event_questions, should_show_question, get_mood_question_text)
from utils.email_service import create_email_verification
from datetime import datetime, timedelta, date, timezone
from services.remember_service import (
    get_user_upcoming_remembers
)
from werkzeug.utils import secure_filename
from extensions import db, bcrypt
import uuid
import os


# User Blueprint
user_bp = Blueprint("user", __name__)

# Profile config
ALLOWED_PROFILE_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "webp"
}

MAX_PROFILE_PIC_SIZE = 2 * 1024 * 1024  # 2MB


# Profile pic
def allowed_profile_pic(filename):
    return (
        filename
        and "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_PROFILE_EXTENSIONS
    )


def save_user_profile_pic(file):

    if not file or not file.filename:
        return None

    if not allowed_profile_pic(file.filename):
        return None

    # Check file size
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)

    if file_size > MAX_PROFILE_PIC_SIZE:
        return None

    extension = secure_filename(
        file.filename
    ).rsplit(".", 1)[1].lower()

    filename = f"{uuid.uuid4().hex}.{extension}"

    upload_folder = os.path.join(
        current_app.static_folder,
        "uploads",
        "profile_pics"
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

    return f"uploads/profile_pics/{filename}"


def delete_user_profile_pic(profile_path):

    if not profile_path:
        return

    full_path = os.path.join(
        current_app.static_folder,
        profile_path
    )

    if os.path.exists(full_path):
        os.remove(full_path)


# Auth
@user_bp.route("/signup/<invite_code>", methods=["GET", "POST"])
def user_signup(invite_code):

    invite = OrgInvite.query.filter_by(
        invite_code=invite_code,
        is_active=True
    ).first()

    if not invite:
        return "Invalid or expired invite link"

    # =========================
    # ⏰ CHECK INVITE EXPIRY
    # =========================
    if invite.expires_at:
        if datetime.utcnow() > invite.expires_at:
            return "This invite link has expired"

    # =========================
    # 🏢 LOAD ORGANIZATION
    # =========================
    org = Organization.query.get(invite.org_id)

    if not org or not org.is_active:
        return "Organization is not active"

    # =========================
    # POST
    # =========================
    if request.method == "POST":

        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")

        # =========================
        # 🔍 BASIC VALIDATION
        # =========================
        if not first_name or not last_name:
            return "First name and last name are required"

        if not email:
            return "Email address is required"

        if not password:
            return "Password is required"

        if len(password) < 8:
            return "Password must be at least 8 characters"

        # =========================
        # 🔍 CHECK EXISTING USER
        # =========================
        existing_user = User.query.filter_by(
            email=email,
            org_id=invite.org_id
        ).first()

        if existing_user:

            # If the account exists but email has not been verified,
            # allow the user to request a fresh verification code.
            if not existing_user.is_email_verified:

                session.clear()
                session["pending_verification_user_id"] = existing_user.id

                create_email_verification(existing_user)

                return redirect(url_for("user.verify_email"))

            return "An account with this email already exists in this organization"

        # =========================
        # 👤 CREATE USER
        # =========================
        user = User(
            org_id=invite.org_id,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            password_hash=bcrypt.generate_password_hash(
                password
            ).decode("utf-8"),
            role="member",
            is_email_verified=False,
            is_onboarded=False,
            is_active=True
        )

        db.session.add(user)
        db.session.commit()

        # =========================
        # 📧 CREATE & SEND OTP
        # =========================
        create_email_verification(user)

        # =========================
        # 🔐 TEMPORARY VERIFICATION SESSION
        # =========================
        session.clear()
        session["pending_verification_user_id"] = user.id

        # =========================
        # ➡️ GO TO EMAIL VERIFICATION
        # =========================
        return redirect(url_for("user.verify_email"))

    return render_template(
        "user_signup.html",
        invite=invite,
        org=org
    )


@user_bp.route("/verify-email", methods=["GET", "POST"])
def verify_email():

    user_id = session.get("pending_verification_user_id")

    if not user_id:
        return redirect(url_for("user.user_login"))

    user = User.query.get(user_id)

    if not user:
        session.clear()
        return redirect(url_for("user.user_login"))

    # =========================
    # ALREADY VERIFIED
    # =========================
    if user.is_email_verified:

        session.clear()

        session["user_id"] = user.id
        session["org_id"] = user.org_id
        session["role"] = user.role

        # Owner → Organization onboarding
        if user.role == "owner":
            return redirect(
                url_for("org.org_onboarding_step_1")
            )

        # Member → User onboarding
        if not user.is_onboarded:
            return redirect(
                url_for("user.user_onboarding")
            )

        return redirect(
            url_for("user.user_dashboard")
        )

    # =========================
    # POST - VERIFY OTP
    # =========================
    if request.method == "POST":

        otp = request.form.get("otp", "").strip()

        # =========================
        # BASIC VALIDATION
        # =========================
        if not otp or len(otp) != 6 or not otp.isdigit():
            return render_template(
                "verify_email.html",
                user=user,
                error="Please enter a valid 6-digit verification code."
            )

        # =========================
        # GET LATEST UNUSED OTP
        # =========================
        verification = EmailVerification.query.filter_by(
            user_id=user.id,
            is_used=False
        ).order_by(
            EmailVerification.created_at.desc()
        ).first()

        if not verification:
            return render_template(
                "verify_email.html",
                user=user,
                error="No active verification code. Please request a new one."
            )

        # =========================
        # CHECK EXPIRY
        # =========================
        if verification.is_expired():
            return render_template(
                "verify_email.html",
                user=user,
                error="This verification code has expired. Please request a new one."
            )

        # =========================
        # CHECK ATTEMPTS
        # =========================
        if verification.attempts >= verification.max_attempts:
            return render_template(
                "verify_email.html",
                user=user,
                error="Too many attempts. Please request a new verification code."
            )

        # =========================
        # VERIFY OTP
        # =========================
        verification.attempts += 1

        if not bcrypt.check_password_hash(
            verification.code_hash,
            otp
        ):
            db.session.commit()

            return render_template(
                "verify_email.html",
                user=user,
                error="Invalid verification code."
            )

        # =========================
        # SUCCESS
        # =========================
        verification.is_used = True
        verification.verified_at = datetime.now(timezone.utc)

        user.is_email_verified = True
        user.email_verified_at = datetime.now(timezone.utc)

        db.session.commit()

        # =========================
        # CREATE AUTH SESSION
        # =========================
        session.clear()

        session["user_id"] = user.id
        session["org_id"] = user.org_id
        session["role"] = user.role

        # =========================
        # CONTINUE BASED ON ROLE
        # =========================

        # Owner → Organization onboarding
        if user.role == "owner":
            return redirect(
                url_for("org.org_onboarding_step_1")
            )

        # Member → User onboarding
        if not user.is_onboarded:
            return redirect(
                url_for("user.user_onboarding")
            )

        # Member already onboarded
        return redirect(
            url_for("user.user_dashboard")
        )

    # =========================
    # GET
    # =========================
    return render_template(
        "verify_email.html",
        user=user
    )


@user_bp.route("/resend-verification", methods=["POST"])
def resend_verification():

    # =========================
    # 🔐 GET PENDING USER
    # =========================
    user_id = session.get("pending_verification_user_id")

    if not user_id:
        return redirect(url_for("user.user_login"))

    user = User.query.get(user_id)

    if not user:
        session.clear()
        return redirect(url_for("user.user_login"))

    # =========================
    # ✅ ALREADY VERIFIED
    # =========================
    if user.is_email_verified:

        session.clear()

        session["user_id"] = user.id
        session["org_id"] = user.org_id
        session["role"] = user.role

        if not user.is_onboarded:
            return redirect(url_for("user.user_onboarding"))

        return redirect(url_for("user.user_dashboard"))

    # =========================
    # 📧 CREATE & SEND NEW OTP
    # =========================
    create_email_verification(user)

    return redirect(url_for("user.verify_email"))


@user_bp.route("/login", methods=["GET", "POST"])
def user_login():
    current_year=datetime.now().year
    if request.method == "POST":

        # =========================
        # 📥 GET LOGIN DETAILS
        # =========================
        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        # =========================
        # 🔍 FIND USER
        # =========================
        user = User.query.filter_by(
            email=email
        ).first()

        if not user:
            flash(
                "Invalid email or password.",
                "error"
            )

            return redirect(
                url_for("user.user_login")
            )

        # user test
        print(f"User deets: role => {user.role} & onboaded => {user.is_onboarded} and email verified => {user.is_email_verified}")
        
        # =========================
        # 🔐 CHECK PASSWORD
        # =========================
        if not bcrypt.check_password_hash(
            user.password_hash,
            password
        ):
            flash(
                "Invalid email or password.",
                "error"
            )

            return redirect(
                url_for("user.user_login")
            )

        # =========================
        # 📧 CHECK EMAIL VERIFICATION
        # =========================
        if not user.is_email_verified:

            # Clear any existing session
            session.clear()

            # Store temporary verification state
            session["pending_verification_user_id"] = user.id

            # Generate and send fresh OTP
            create_email_verification(user)

            flash(
                "Please verify your email to continue.",
                "info"
            )

            return redirect(
                url_for("user.verify_email")
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


        # =========================
        # 🔐 START AUTHENTICATED SESSION
        # =========================

        session.clear()

        session["user_id"] = user.id
        session["org_id"] = user.org_id
        session["role"] = user.role


        # =========================
        # 👤 CHECK USER STATUS
        # =========================

        if not user.is_onboarded:

            # =========================
            # 🚦 ROLE-BASED REDIRECT
            # =========================
            if user.role in ["owner"]:

                flash(
                "Your account is unboarded. Please complete your onboarding to continue.",
                "info"
                )

                return redirect(
                    url_for("org.org_onboarding_step_1")
                )

            elif user.role in ["member", "admin"]:

                flash(
                "Your account is unboarded. Please complete your onboarding to continue.",
                "info")

                return redirect(
                    url_for("user.user_onboarding")
                )


        # =========================
        # 📊 UPDATE LAST LOGIN
        # =========================
        user.last_login = datetime.now(
            timezone.utc
        )

        db.session.commit()

        # =========================
        # 🚦 ROLE-BASED REDIRECT
        # =========================
        if user.role in ["owner"]:

            return redirect(
                url_for("org.org_dashboard")
            )

        elif user.role in ["member", "admin"]:

            return redirect(
                url_for("user.user_dashboard")
            )

        # =========================
        # ❌ INVALID ROLE
        # =========================
        flash(
            "Your account has an invalid role. Please contact your administrator.",
            "error"
        )

        session.clear()

        return redirect(
            url_for("user.user_login")
        )

    return render_template(
        "login.html", current_year=current_year)


@user_bp.route("/logout")
def logout():

    session.pop("user_id", None)
    session.pop("org_id", None)

    session.clear()  # optional safety net

    return redirect(url_for("user.user_login"))


@user_bp.route("/user/onboarding", methods=["GET", "POST"])
def user_onboarding():

    user_id = session.get("user_id")

    # =========================
    # 🔐 AUTH CHECK
    # =========================

    if not user_id:
        return redirect(url_for("user.user_login"))

    user = User.query.get(user_id)

    if not user:
        session.clear()
        return redirect(url_for("user.user_login"))

    # =========================
    # 📧 EMAIL VERIFICATION
    # =========================

    if not user.is_email_verified:

        session.clear()
        session["pending_verification_user_id"] = user.id

        return redirect(
            url_for("user.verify_email")
        )

    # =========================
    # ✅ ALREADY ONBOARDED
    # =========================

    if user.is_onboarded:
        return redirect(
            url_for("user.user_dashboard")
        )

    # =========================
    # ⚙️ GET / CREATE SETTINGS
    # =========================

    settings = user.settings

    if not settings:

        settings = UserSettings(
            user_id=user.id
        )

        db.session.add(settings)
        db.session.flush()

    # =========================
    # 🏢 LOAD DEPARTMENTS
    # =========================

    departments = Department.query.filter_by(
        org_id=user.org_id
    ).all()

    # =========================
    # POST
    # =========================

    if request.method == "POST":

        # =========================
        # CORE ONBOARDING DATA
        # =========================

        dob = request.form.get("dob", "").strip()
        department_id = request.form.get("department_id")
        consent_given = request.form.get("consent_given")

        # =========================
        # REQUIRED FIELD VALIDATION
        # =========================

        if not dob:
            return "Date of birth is required"

        # Department is required only
        # when the organization has departments

        if departments and not department_id:
            return "Please select your department or group"

        # Consent is required

        if not consent_given:
            return "Please agree to receive personalized communications"

        # =========================
        # DATE VALIDATION
        # =========================

        try:

            parsed_dob = datetime.strptime(
                dob,
                "%Y-%m-%d"
            ).date()

        except ValueError:

            return "Please enter a valid date of birth"

        # Prevent future DOB

        if parsed_dob > date.today():
            return "Date of birth cannot be in the future"

        # =========================
        # SAVE DOB
        # =========================

        user.date_of_birth = parsed_dob

        # =========================
        # SAVE CONSENT
        # =========================

        settings.consent_given = True
        settings.consent_given_at = datetime.now(timezone.utc)

        # =========================
        # DEPARTMENT
        # =========================

        if departments:

            try:
                department_id = int(department_id)

            except (TypeError, ValueError):
                return "Invalid department selection"

            department = Department.query.filter_by(
                id=department_id,
                org_id=user.org_id
            ).first()

            if not department:
                return "Invalid department selection"

            # Clear previous memberships

            UserDepartment.query.filter_by(
                user_id=user.id
            ).delete(
                synchronize_session=False
            )

            # Add primary department

            db.session.add(
                UserDepartment(
                    user_id=user.id,
                    department_id=department.id
                )
            )

        # =========================
        # COMPLETE ONBOARDING
        # =========================

        user.is_onboarded = True
        user.onboarding_completed_at = datetime.now(timezone.utc)

        db.session.commit()

        # =========================
        # GO TO DASHBOARD
        # =========================

        return redirect(
            url_for("user.user_dashboard")
        )

    # =========================
    # GET
    # =========================

    return render_template(
        "onboarding/user_onboarding.html",
        user=user,
        settings=settings,
        departments=departments
    )



# =================================
# USER DASHBOARD
# =================================
@user_bp.route("/user/dashboard")
def user_dashboard():

    # =========================
    # 🔐 AUTH CHECK
    # =========================

    user_id = session.get("user_id")

    if not user_id:
        return redirect(
            url_for("user.user_login")
        )

    user = User.query.get(user_id)

    if not user:
        session.clear()

        return redirect(
            url_for("user.user_login")
        )

    # =========================
    # 📧 EMAIL VERIFICATION
    # =========================

    if not user.is_email_verified:

        session.clear()

        session["pending_verification_user_id"] = user.id

        return redirect(
            url_for("user.verify_email")
        )

    # =========================
    # 📝 ONBOARDING ENFORCEMENT
    # =========================

    if not user.is_onboarded:

        return redirect(
            url_for("user.user_onboarding")
        )

    # =========================
    # 🏢 ORGANIZATION
    # =========================

    org = Organization.query.get(
        user.org_id
    )

    if not org:
        return "Organization not found", 404

    if not org.is_active:
        return "Organization is not active", 403

    # =========================
    # ⚙️ USER SETTINGS
    # =========================

    settings = user.settings

    # =========================
    # 📅 DAYS AT ORGANIZATION
    # =========================

    days_at_org = None

    if user.joined_date:
        days_at_org = (
            date.today() - user.joined_date
        ).days

    # =========================
    # 🧠 REMEMBERS
    # =========================

    upcoming_remembers = get_user_upcoming_remembers(
        user=user,
        org=org
    )

    # =========================
    # 📊 DASHBOARD
    # =========================

    return render_template(
        "user_dashboard.html",
        user=user,
        org=org,
        settings=settings,
        days_at_org=days_at_org,
        upcoming_remembers=upcoming_remembers
    )


# =========================
# 👤 USER PROFILE / SETTINGS
# =========================
@user_bp.route("/user/profile", methods=["GET", "POST"])
def user_profile():

    # =========================
    # AUTH CHECK
    # =========================
    user_id = session.get("user_id")

    if not user_id:
        return redirect(
            url_for("user.user_login")
        )

    # =========================
    # LOAD USER
    # =========================
    user = User.query.get(user_id)

    if not user:
        session.clear()

        return redirect(
            url_for("user.user_login")
        )

    # =========================
    # EMAIL VERIFICATION
    # =========================
    if not user.is_email_verified:

        session.clear()

        session["pending_verification_user_id"] = user.id

        return redirect(
            url_for("user.verify_email")
        )

    # =========================
    # ORGANIZATION
    # =========================
    org = Organization.query.get(
        user.org_id
    )

    if not org or not org.is_active:
        return "Organization not available", 403

    # =========================
    # USER SETTINGS
    # =========================
    settings = user.settings

    # Create settings if missing
    if not settings:

        settings = UserSettings(
            user_id=user.id
        )

        db.session.add(settings)
        db.session.commit()

    # =========================
    # SAVE PROFILE
    # =========================
    if request.method == "POST":

        # ---------------------------------
        # CORE PROFILE
        # ---------------------------------
        first_name = request.form.get(
            "first_name",
            ""
        ).strip()

        last_name = request.form.get(
            "last_name",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip()

        phone = request.form.get(
            "phone",
            ""
        ).strip()

        date_of_birth = request.form.get(
            "date_of_birth",
            ""
        ).strip()

        date_joined = request.form.get(
            "date_joined",
            ""
        ).strip()

        # ---------------------------------
        # BASIC VALIDATION
        # ---------------------------------
        if not first_name or not last_name:
            flash(
                "First name and last name are required.",
                "error"
            )

            return redirect(
                url_for("user.user_profile")
            )

        if not email:
            flash(
                "Email is required.",
                "error"
            )

            return redirect(
                url_for("user.user_profile")
            )

        # ---------------------------------
        # EMAIL CHECK
        # ---------------------------------
        existing_user = User.query.filter(
            User.email == email,
            User.org_id == user.org_id,
            User.id != user.id
        ).first()

        if existing_user:

            flash(
                "Email already exists in this organization.",
                "error"
            )

            return redirect(
                url_for("user.user_profile")
            )

        # ---------------------------------
        # UPDATE CORE PROFILE
        # ---------------------------------
        user.first_name = first_name
        user.last_name = last_name
        user.email = email
        user.phone = phone

        # ---------------------------------
        # DATE OF BIRTH
        # ---------------------------------
        if date_of_birth:

            try:
                user.date_of_birth = datetime.strptime(
                    date_of_birth,
                    "%Y-%m-%d"
                ).date()

            except ValueError:

                flash(
                    "Please enter a valid date of birth.",
                    "error"
                )

                return redirect(
                    url_for("user.user_profile")
                )

        else:

            user.date_of_birth = None

        # ---------------------------------
        # DATE JOINED
        # ---------------------------------
        if date_joined:

            try:
                user.joined_date = datetime.strptime(
                    date_joined,
                    "%Y-%m-%d"
                ).date()

            except ValueError:

                flash(
                    "Please enter a valid date joined.",
                    "error"
                )

                return redirect(
                    url_for("user.user_profile")
                )

        else:

            user.joined_date = None

        # ---------------------------------
        # PROFILE PICTURE
        # ---------------------------------
        remove_profile_pic = (
            request.form.get("remove_profile_pic") == "1"
        )

        profile_pic_file = request.files.get(
            "profile_pic"
        )

        if remove_profile_pic:

            if user.profile_pic:
                delete_user_profile_pic(
                    user.profile_pic
                )

            user.profile_pic = None

        elif profile_pic_file and profile_pic_file.filename:

            new_profile_pic = save_user_profile_pic(
                profile_pic_file
            )

            if not new_profile_pic:

                flash(
                    "Please upload a valid profile picture "
                    "(PNG, JPG, JPEG or WEBP, max 2MB).",
                    "error"
                )

                return redirect(
                    url_for("user.user_profile")
                )

            # Remove old picture after new one
            # has been successfully saved
            if user.profile_pic:
                delete_user_profile_pic(
                    user.profile_pic
                )

            user.profile_pic = new_profile_pic

        # ---------------------------------
        # PERSONAL SETTINGS
        # ---------------------------------
        settings.gender = request.form.get(
            "gender"
        )

        settings.marital_status = request.form.get(
            "marital_status"
        )

        settings.nationality = request.form.get(
            "nationality"
        )

        settings.state = request.form.get(
            "state"
        )

        settings.religion = request.form.get(
            "religion"
        )

        settings.bio = request.form.get(
            "bio",
            ""
        ).strip()

        settings.timezone = request.form.get(
            "timezone",
            "Africa/Lagos"
        )

        settings.preferred_channel = request.form.get(
            "preferred_channel",
            "email"
        )

        settings.language = request.form.get(
            "language",
            "en"
        )

        settings.tone_preference = request.form.get(
            "tone_preference",
            "friendly"
        )

        settings.receive_faith_messages = (
            request.form.get(
                "receive_faith_messages"
            ) == "1"
        )

        # ---------------------------------
        # NOTIFICATIONS
        # ---------------------------------
        user.receive_notifications = (
            request.form.get(
                "receive_notifications"
            ) == "1"
        )

        user.message_frequency = request.form.get(
            "message_frequency",
            "weekly"
        )

        # ---------------------------------
        # SAVE EVERYTHING
        # ---------------------------------
        db.session.commit()

        flash(
            "Your profile was updated successfully.",
            "success"
        )

        return redirect(
            url_for("user.user_profile")
        )

    return render_template(
        "user/user_profile.html",
        user=user,
        org=org,
        settings=settings
    )



# =================================
# USER REMEMBERS
# =================================
@user_bp.route("/user/remembers")
def user_remembers():

    # =========================
    # 🔐 AUTH CHECK
    # =========================

    user_id = session.get("user_id")

    if not user_id:
        flash("Please log in to continue.", "error")
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

    # =========================
    # 📧 EMAIL VERIFICATION
    # =========================

    if not user.is_email_verified:

        session.clear()

        session["pending_verification_user_id"] = user.id

        return redirect(
            url_for("user.verify_email")
        )

    # =========================
    # 📝 ONBOARDING ENFORCEMENT
    # =========================

    if not user.is_onboarded:
        return redirect(
            url_for("user.user_onboarding")
        )

    # =========================
    # 🏢 ORGANIZATION
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

    # =========================
    # 🧠 ALL REMEMBERS
    # =========================

    all_remembers = get_user_upcoming_remembers(
        user=user,
        org=org
    )

    # =========================
    # 📊 SOURCE COUNTS
    # =========================

    personal_count = sum(
        1 for item in all_remembers
        if item.get("source") == "personal"
    )

    organization_count = sum(
        1 for item in all_remembers
        if item.get("source") == "organization"
    )

    shared_count = sum(
        1 for item in all_remembers
        if item.get("source") == "shared"
    )

    total_count = len(all_remembers)

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
    # 🏷️ AVAILABLE TYPES
    # =========================

    type_options = sorted(
        {
            item.get("type")
            for item in all_remembers
            if item.get("type")
        }
    )

    # =========================
    # 📄 PAGINATION
    # =========================

    page = request.args.get(
        "page",
        1,
        type=int
    )

    per_page = 5

    total_items = len(filtered_remembers)

    total_pages = max(
        1,
        (total_items + per_page - 1) // per_page
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
    # 📤 RESPONSE
    # =========================

    return render_template(
        "user/user_remembers.html",

        user=user,
        org=org,

        remembers=paginated_remembers,

        personal_count=personal_count,
        organization_count=organization_count,
        shared_count=shared_count,
        total_count=total_count,

        source_filter=source_filter,
        type_filter=type_filter,
        type_options=type_options,

        page=page,
        total_pages=total_pages,
        total_items=total_items,
        per_page=per_page,

        has_prev=page > 1,
        has_next=page < total_pages,

        prev_page=page - 1,
        next_page=page + 1
    )


# =================================
# USER REMEMBER TYPES
# =================================

USER_REMEMBER_TYPES = {
    "personal",
    "anniversary",
    "milestone",
    "other"
}


# =================================
# ADD USER REMEMBER
# =================================

@user_bp.route("/user/remembers/add", methods=["POST"])
def add_user_remember():

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

    if not user.is_email_verified:

        session.clear()

        session["pending_verification_user_id"] = user.id

        return redirect(
            url_for("user.verify_email")
        )

    if not user.is_onboarded:
        return redirect(
            url_for("user.user_onboarding")
        )

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

    name = request.form.get(
        "name",
        ""
    ).strip()

    remember_date = request.form.get(
        "date",
        ""
    ).strip()

    remember_type = request.form.get(
        "remember_type",
        "personal"
    ).strip()

    is_public = request.form.get("is_public") == "on"

    is_recurring = (
        request.form.get("is_recurring") == "on"
    )

    # =========================
    # VALIDATION
    # =========================

    if not name:

        flash(
            "Please enter a name for the Remember.",
            "error"
        )

        return redirect(
            url_for("user.user_remembers")
        )

    if not remember_date:

        flash(
            "Please select a date.",
            "error"
        )

        return redirect(
            url_for("user.user_remembers")
        )

    try:

        parsed_date = datetime.strptime(
            remember_date,
            "%Y-%m-%d"
        ).date()

    except ValueError:

        flash(
            "Please enter a valid date.",
            "error"
        )

        return redirect(
            url_for("user.user_remembers")
        )

    if remember_type not in USER_REMEMBER_TYPES:
        remember_type = "personal"

    # =========================
    # CREATE
    # =========================

    remember = UserRemember(
        user_id=user.id,
        name=name,
        date=parsed_date,
        remember_type=remember_type,
        is_recurring=is_recurring,
        is_public=is_public,
        is_active=True
    )

    db.session.add(remember)

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        flash(
            "We couldn't save your Remember. Please try again.",
            "error"
        )

        return redirect(
            url_for("user.user_remembers")
        )

    flash(
        f'"{name}" has been added to your Remembers.',
        "success"
    )

    return redirect(
        url_for("user.user_remembers")
    )


# =================================
# EDIT USER REMEMBER
# =================================

@user_bp.route("/user/remembers/<int:remember_id>/edit",methods=["POST"])
def edit_user_remember(remember_id):

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

    if not user.is_email_verified:

        session.clear()

        session["pending_verification_user_id"] = user.id

        return redirect(
            url_for("user.verify_email")
        )

    if not user.is_onboarded:

        return redirect(
            url_for("user.user_onboarding")
        )

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

    # =========================
    # OWNERSHIP CHECK
    # =========================

    remember = UserRemember.query.filter_by(
        id=remember_id,
        user_id=user.id,
        is_active=True
    ).first()

    if not remember:

        flash(
            "That Remember could not be found.",
            "error"
        )

        return redirect(
            url_for("user.user_remembers")
        )

    name = request.form.get(
        "name",
        ""
    ).strip()

    remember_date = request.form.get(
        "date",
        ""
    ).strip()

    remember_type = request.form.get(
        "remember_type",
        "personal"
    ).strip()

    is_public = (
    request.form.get("is_public") == "on"
    )

    is_recurring = (
        request.form.get("is_recurring") == "on"
    )

    # =========================
    # VALIDATION
    # =========================

    if not name:

        flash(
            "Please enter a name for the Remember.",
            "error"
        )

        return redirect(
            url_for("user.user_remembers")
        )

    if not remember_date:

        flash(
            "Please select a date.",
            "error"
        )

        return redirect(
            url_for("user.user_remembers")
        )

    try:

        parsed_date = datetime.strptime(
            remember_date,
            "%Y-%m-%d"
        ).date()

    except ValueError:

        flash(
            "Please enter a valid date.",
            "error"
        )

        return redirect(
            url_for("user.user_remembers")
        )

    if remember_type not in USER_REMEMBER_TYPES:
        remember_type = "personal"

    # =========================
    # UPDATE
    # =========================

    remember.name = name
    remember.date = parsed_date
    remember.remember_type = remember_type
    remember.is_recurring = is_recurring
    remember.is_public = is_public

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        flash(
            "We couldn't update your Remember. Please try again.",
            "error"
        )

        return redirect(
            url_for("user.user_remembers")
        )

    flash(
        f'"{name}" has been updated.',
        "success"
    )

    return redirect(
        url_for("user.user_remembers")
    )


# =================================
# DELETE / DEACTIVATE USER REMEMBER
# =================================

@user_bp.route("/user/remembers/<int:remember_id>/delete", methods=["POST"])
def delete_user_remember(remember_id):

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

    if not user.is_email_verified:

        session.clear()

        session["pending_verification_user_id"] = user.id

        return redirect(
            url_for("user.verify_email")
        )

    if not user.is_onboarded:

        return redirect(
            url_for("user.user_onboarding")
        )

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

    # =========================
    # OWNERSHIP CHECK
    # =========================

    remember = UserRemember.query.filter_by(
        id=remember_id,
        user_id=user.id,
        is_active=True
    ).first()

    if not remember:

        flash(
            "That Remember could not be found.",
            "error"
        )

        return redirect(
            url_for("user.user_remembers")
        )

    remember_name = remember.name

    # =========================
    # SOFT DELETE
    # =========================

    remember.is_active = False

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        flash(
            "We couldn't remove that Remember. Please try again.",
            "error"
        )

        return redirect(
            url_for("user.user_remembers")
        )

    flash(
        f'"{remember_name}" has been removed from your Remembers.',
        "success"
    )

    return redirect(
        url_for("user.user_remembers")
    )



@user_bp.route("/members")
def list_members():

    org_id = session.get("org_id")

    if not org_id:
        return redirect(url_for("org.org_login"))

    # page number from URL (?page=1, ?page=2, etc.)
    page = request.args.get("page", 1, type=int)

    per_page = 5

    members_pagination = User.query.filter_by(
        org_id=org_id
    ).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )

    departments = Department.query.filter_by(
        org_id=org_id
    ).all()
    members = User.query.filter_by(org_id=org_id).all()
    # total users
    total_members = len(members)

    return render_template(
        "members.html",
        members=members_pagination.items,
        pagination=members_pagination,
        departments=departments,
        total_members=total_members
    )


@user_bp.route("/members/<int:user_id>/update", methods=["POST"])
def update_member(user_id):

    org_id = session.get("org_id")
    current_user_id = session.get("user_id")

    if not org_id or not current_user_id:
        return redirect(url_for("org.org_login"))

    # =========================
    # LOAD CURRENT USER
    # =========================
    current_user = User.query.filter_by(
        id=current_user_id,
        org_id=org_id
    ).first()

    if not current_user:
        session.clear()
        return redirect(url_for("org.org_login"))

    # =========================
    # LOAD MEMBER
    # =========================
    user = User.query.filter_by(
        id=user_id,
        org_id=org_id
    ).first_or_404()

    # =========================
    # EMAIL VALIDATION
    # =========================
    new_email = request.form.get("email", "").strip()
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()

    existing_user = User.query.filter(
        User.email == new_email,
        User.org_id == org_id,
        User.id != user.id
    ).first()

    if existing_user:
        flash("Email already exists", "error")
        return redirect(request.referrer)

    user.email = new_email
    user.first_name = first_name
    user.last_name = last_name


    # =========================
    # DOB
    # =========================
    dob = request.form.get("date_of_birth")

    if dob:
        try:
            user.date_of_birth = datetime.strptime(
                dob,
                "%Y-%m-%d"
            ).date()
        except ValueError:
            flash("Invalid date of birth.", "error")
            return redirect(request.referrer)
    else:
        user.date_of_birth = None

    # =========================
    # DEPARTMENTS
    # =========================
    dept_ids = request.form.getlist("department_ids")

    # Remove old department memberships
    UserDepartment.query.filter_by(
        user_id=user.id
    ).delete()

    # Add selected departments
    for dept_id in dept_ids:

        try:
            dept_id = int(dept_id)
        except ValueError:
            continue

        dept = Department.query.filter_by(
            id=dept_id,
            org_id=org_id
        ).first()

        if dept:
            db.session.add(
                UserDepartment(
                    user_id=user.id,
                    department_id=dept.id
                )
            )

    # =========================
    # ROLE MANAGEMENT
    # =========================
    new_role = request.form.get("role")

    if new_role and new_role != user.role:

        # Only owners and admins can change roles
        if current_user.role not in ["owner", "admin"]:
            flash(
                "You do not have permission to change member roles.",
                "error"
            )
            return redirect(
                url_for(
                    "user.member_detail",
                    user_id=user.id
                )
            )

        allowed_roles = ["owner", "admin", "member"]

        if new_role not in allowed_roles:
            flash("Invalid role selected.", "error")
            return redirect(
                url_for(
                    "user.member_detail",
                    user_id=user.id
                )
            )

        user.role = new_role

    db.session.commit()

    flash(
        "Member updated successfully",
        "success"
    )

    return redirect(
        url_for(
            "user.member_detail",
            user_id=user.id
        )
    )


@user_bp.route("/members/<int:user_id>")
def member_detail(user_id):

    org_id = session.get("org_id")
    if not org_id:
        return redirect(url_for("org.org_login"))

    user = User.query.filter_by(id=user_id, org_id=org_id).first_or_404()
    print(f"user deets => {user.departments}")

    return render_template("member_detail.html", user=user)


@user_bp.route("/members/<int:user_id>/update-department", methods=["POST"])
def update_member_department(user_id):

    org_id = session.get("org_id")

    if not org_id:
        return redirect(url_for("org.org_login"))

    # Get the member and make sure they belong to this organization
    user = User.query.filter_by(
        id=user_id,
        org_id=org_id
    ).first_or_404()

    dept_id = request.form.get("department_id")

    # Remove existing department assignment
    UserDepartment.query.filter_by(
        user_id=user.id
    ).delete()

    # Assign new department if one was selected
    if dept_id:

        try:
            dept_id = int(dept_id)
        except ValueError:
            flash("Invalid department selected.", "error")
            return redirect(
                url_for(
                    "user.member_detail",
                    user_id=user.id
                )
            )

        # Make sure the department belongs to this organization
        department = Department.query.filter_by(
            id=dept_id,
            org_id=org_id
        ).first()

        if not department:
            flash("Invalid department selected.", "error")
            return redirect(
                url_for(
                    "user.member_detail",
                    user_id=user.id
                )
            )

        db.session.add(
            UserDepartment(
                user_id=user.id,
                department_id=department.id
            )
        )

    db.session.commit()

    flash("Department updated successfully", "success")

    return redirect(
        url_for(
            "user.member_detail",
            user_id=user.id
        )
    )


@user_bp.route("/members/<int:user_id>/delete", methods=["POST"])
def delete_member(user_id):

    org_id = session.get("org_id")

    user = User.query.filter_by(id=user_id, org_id=org_id).first_or_404()

    db.session.delete(user)
    db.session.commit()

    flash("Member deleted successfully", "success")

    return redirect(url_for("user.list_members"))


@user_bp.route("/user/checkin", methods=["GET"])
def user_checkin():
    # 👤 load user
    user_id = session.get("user_id")
    current_user = User.query.get(user_id)
    
    # 🔐 auth check
    if not user_id or not current_user:
        return redirect("/login")

    # 1. Get active check-in event
    events = get_active_checkin_events(current_user.org_id)
    if not events:
        return render_template("user/checkin.html", event=None, questions=[])
    
    event = events[0]  # assuming 1 default check-in event

    # 2. Get questions
    all_questions = get_event_questions(event.id)

    # 3. Load today's answers
    today_answers = {
        r.question_id: r.answer
        for r in EventResponse.query.filter_by(
            user_id=current_user.id,
            event_id=event.id,
            submitted_for_date=date.today()
        ).all()
    }

    # =====================
    # NEW: Dynamic Mood Question based on user frequency
    # =====================
    for q in all_questions:
        if q.question_key == "mood_check":
            q.question_text = get_mood_question_text(current_user.message_frequency)
            break

    # 4. Filter visible questions (conditional logic)
    visible_questions = [
        q for q in all_questions
        if should_show_question(q, today_answers)
    ]

    return render_template("user/checkin.html", 
                           event=event, 
                           questions=visible_questions, 
                           answers=today_answers)

@user_bp.route("/checkin/submit", methods=["POST"])
def submit_checkin():

    user_id = session.get("user_id")
    current_user = User.query.get(user_id)

    if not user_id or not current_user:
        return redirect("/login")

    # ✅ FIX 1: ensure int
    event_id = request.form.get("event_id")

    try:
        event_id = int(event_id)
    except (TypeError, ValueError):
        flash("Invalid event", "error")
        return redirect(url_for("user.user_checkin"))

    questions = get_event_questions(event_id)

    for key in request.form:
        print("FORM KEY:", key, "VALUE:", request.form.getlist(key))

    for q in questions:

        answer = request.form.get(f"q_{q.id}")
        #answer = request.form.getlist(f"q_{q.id}[]")

        print(f"User checkin Q{q.id} -> Answer: {answer}")

        if not answer:
            continue

        existing = EventResponse.query.filter_by(
            user_id=current_user.id,
            event_id=event_id,
            question_id=q.id,
            submitted_for_date=date.today()
        ).first()

        if existing:
            existing.answer = answer
        else:
            db.session.add(EventResponse(
                user_id=current_user.id,
                event_id=event_id,
                question_id=q.id,
                answer=answer,
                submitted_for_date=date.today()
            ))

    db.session.commit()

    flash("Check-in submitted successfully 💚")
    return redirect(url_for("user.user_checkin"))


@user_bp.route("/user/checkin_history")
def checkin_history():
    user_id = session.get("user_id")
    current_user = User.query.get(user_id)
    
    if not current_user:
        return redirect("/login")

    page = request.args.get('page', 1, type=int)
    per_page = 5

    responses = EventResponse.query.filter_by(
        user_id=current_user.id
    ).order_by(
        EventResponse.submitted_for_date.desc(),
        EventResponse.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    from collections import defaultdict
    checkins = defaultdict(dict)

    for r in responses.items:
        date_key = r.submitted_for_date.strftime("%Y-%m-%d")
        display_date = r.submitted_for_date.strftime("%A, %B %d, %Y")
        time_str = r.created_at.strftime("%I:%M %p") if r.created_at else ""

        if date_key not in checkins:
            checkins[date_key] = {
                'display_date': display_date,
                'time': time_str,
                'answers': {}
            }
        
        checkins[date_key]['answers'][r.question.question_text] = r.answer

    return render_template("user/my_checkins.html", 
                           checkins=dict(checkins),   # convert defaultdict to dict
                           pagination=responses)


# =================================
# USER NOTIFICATIONS
# =================================
@user_bp.route("/user/notifications")
def user_notifications():

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

    if not user.is_email_verified:

        session.clear()

        session["pending_verification_user_id"] = user.id

        return redirect(
            url_for("user.verify_email")
        )

    if not user.is_onboarded:
        return redirect(
            url_for("user.user_onboarding")
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

    if not org.is_active:

        flash(
            "Your organization is currently inactive.",
            "error"
        )

        return redirect(
            url_for("user.user_login")
        )

    notifications = (
        Notification.query
        .filter_by(
            user_id=user.id,
            org_id=org.id,
            context="user"
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
        "user/user_notifications.html",
        user=user,
        org=org,
        notifications=notifications,
        unread_count=unread_count
    )


# =================================
# MARK USER NOTIFICATION AS READ
# =================================
@user_bp.route("/user/notifications/<int:notification_id>/read", methods=["POST"])
def mark_user_notification_read(notification_id):

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

    if not user.is_email_verified:
        session.clear()
        session["pending_verification_user_id"] = user.id

        return redirect(
            url_for("user.verify_email")
        )

    if not user.is_onboarded:
        return redirect(
            url_for("user.user_onboarding")
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

    if not org.is_active:
        flash(
            "Your organization is currently inactive.",
            "error"
        )

        return redirect(
            url_for("user.user_login")
        )

    notification = Notification.query.filter_by(
        id=notification_id,
        user_id=user.id,
        org_id=org.id,
        context="user"
    ).first()

    if not notification:
        flash(
            "Notification could not be found.",
            "error"
        )

        return redirect(
            url_for("user.user_notifications")
        )

    if not notification.is_read:

        notification.is_read = True
        notification.read_at = datetime.now(timezone.utc)

        db.session.commit()

    return redirect(
        url_for("user.user_notifications")
    )

