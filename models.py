from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, date, timezone
from extensions import db
import secrets

ALLOWED_FREQUENCIES = ["daily", "weekly", "bi-weekly", "monthly"]
#WAT = timezone(timedelta(hours=1))  # West Africa Time

# =========================
# 🏢 ORGANIZATION
# =========================
class Organization(db.Model):
    __tablename__ = "organizations"

    id = db.Column(db.Integer, primary_key=True)

    # CORE IDENTITY
    name = db.Column(db.String(150), nullable=False)
    slug = db.Column(db.String(150), unique=True, nullable=False)
    plan = db.Column(db.String(50), default="free")

    org_type = db.Column(db.String(50))
    industry = db.Column(db.String(100))
    location = db.Column(db.String(100))
    country = db.Column(db.String(100))
    slogan = db.Column(db.Text)
    logo = db.Column(db.String(255))

    # FLAGS
    is_verified = db.Column(db.Boolean, default=False)
    onboarding_completed = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    timezone = db.Column(db.String(100),default="Africa/Lagos")

    # RELATIONSHIPS
    users = db.relationship("User", backref="organization", lazy=True)
    events = db.relationship("Event", backref="organization", lazy=True)
    templates = db.relationship("MessageTemplate", backref="organization", lazy=True)
    settings = db.relationship("OrgSettings", backref="organization", uselist=False)
    remembers = db.relationship("Remember", backref="organization", lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Org {self.name}>"

# =========================
# ORG_SETTINGS
# =========================
class OrgSettings(db.Model):
    __tablename__ = "org_settings"

    id = db.Column(db.Integer, primary_key=True)

    org_id = db.Column(db.Integer, db.ForeignKey("organizations.id", name="fk__org_orgsettings"), unique=True)

    # COMMUNICATION
    comm_type = db.Column(db.String(100))  # email, sms, whatsapp, mixed
    timezone = db.Column(db.String(50), default="Africa/Lagos")

    # STRUCTURE (now proper relational via Department table)
    default_view = db.Column(db.String(50), default="all")

    # ENGAGEMENT SETTINGS (VERY IMPORTANT for your app)
    checkin_frequency = db.Column(db.String(50), default="weekly")
    reminder_enabled = db.Column(db.Boolean, default=True)

    # FUTURE EXTENSIONS
    allow_self_join = db.Column(db.Boolean, default=False)
    require_approval = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<OrgSettings for Org {self.org_id}>"

# =========================
# ORG_DEPARTMENTS
# =========================
class Department(db.Model):
    __tablename__ = "departments"

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("organizations.id", name="fk_orgdepartment_department"), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    slug = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # relationships
    organization = db.relationship("Organization", backref="departments")
    #users = db.relationship("User", back_populates="department")
    members = db.relationship("UserDepartment", backref="department", lazy=True,cascade="all, delete-orphan")

    __table_args__ = (
    db.UniqueConstraint('org_id', 'name', name='uq_department_org_name'),)

    def __repr__(self):
        return f"<Department {self.name}>"


# =========================
# 👤 USER DEPARTMENTS
# =========================
class UserDepartment(db.Model):
    __tablename__ = "user_departments"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id", name="fk_userdepartment_user"), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id", name="fk_userdepartment_department"), nullable=False)
    joined_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint(
            'user_id',
            'department_id',
            name='uq_user_department'
        ),
    )


# =========================
# 👤 USER (CORE MODEL)
# =========================
class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer,db.ForeignKey("organizations.id", name="fk_user_org"), nullable=False)

    # AUTH / IDENTITY
    first_name = db.Column(db.String(255))
    last_name = db.Column(db.String(255))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(150), nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    # CORE PROFILE (used in system remember triggers)
    date_of_birth = db.Column(db.Date)
    joined_date = db.Column(db.Date)

    # RELATIONAL STRUCTURE
    departments = db.relationship("UserDepartment", backref="user", lazy=True, cascade="all, delete-orphan")

    # PROFILE MEDIA
    profile_pic = db.Column(db.String(255))

    # SYSTEM FLAGS
    role = db.Column(db.String(50), nullable=False, default="member")
    is_onboarded = db.Column(db.Boolean, default=False)
    onboarding_completed_at = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    is_email_verified = db.Column(db.Boolean, nullable=False, default=False)
    email_verified_at = db.Column(db.DateTime)


    # ENGAGEMENT CONTROL
    message_frequency = db.Column(db.String(20), default="weekly")
    receive_notifications = db.Column(db.Boolean, default=True)

    # CONSENT (IMPORTANT FOR COMMUNICATION SYSTEMS)
    #consent_given = db.Column(db.Boolean, default=False)

    # TRACKING
    last_login = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # RELATIONSHIPS
    messages = db.relationship("MessageLog", backref="user", lazy=True)
    #responses = db.relationship("EventResponse", backref="user", lazy=True)
    responses = db.relationship("EventResponse", back_populates="user", lazy=True, cascade="all, delete-orphan")
    

    __table_args__ = (
        db.UniqueConstraint('email', 'org_id', name='uq_user_email_org'),
        db.Index('idx_user_org', 'org_id'),
        db.Index('idx_user_dob', 'date_of_birth'),
        db.Index('idx_user_joined_date', 'joined_date'),
    )

    def get_settings(self):
        return self.settings

    def __repr__(self):
        return f"<User {self.email}>"


# =========================
# ⚙️ USER SETTINGS / PROFILE EXTENSION
# =========================
class UserSettings(db.Model):
    __tablename__ = "user_settings"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id", name="fk_user_usersettings"), nullable=False, unique=True)

    # DEMOGRAPHIC / PERSONALIZATION
    gender = db.Column(db.String(20))
    marital_status = db.Column(db.String(50))
    nationality = db.Column(db.String(50))
    state = db.Column(db.String(50))
    religion = db.Column(db.String(50))

    # PROFILE CUSTOMIZATION
    bio = db.Column(db.Text)
    timezone = db.Column(db.String(50), default="Africa/Lagos")

    # COMMUNICATION PREFERENCES (optional overrides)
    preferred_channel = db.Column(db.String(50), default="email")  # email, push, sms
    receive_faith_messages = db.Column(db.Boolean, nullable=False, default=True)

    # SYSTEM PERSONALIZATION (future AI layer)
    tone_preference = db.Column(db.String(50), default="friendly")
    language = db.Column(db.String(50), default="en")

    # METADATA
    #updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    consent_given = db.Column(db.Boolean, default=False)
    consent_given_at = db.Column(db.DateTime)

    # RELATIONSHIP
    user = db.relationship("User", backref=db.backref("settings", uselist=False))

    def __repr__(self):
        return f"<UserSettings user_id={self.user_id}>"



# =========================
#  REMEMBER 
# =========================
class Remember(db.Model):
    __tablename__ = "remembers"

    id = db.Column(db.Integer, primary_key=True)

    org_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)

    name = db.Column(db.String(150), nullable=False)

    date = db.Column(db.Date, nullable=False)

    remember_type = db.Column(db.String(50), nullable=False)

    is_recurring = db.Column(db.Boolean, default=True)
    is_active = db.Column(db.Boolean, default=True)

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc)
    )



class UserRemember(db.Model):
    __tablename__ = "user_remembers"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", name="fk_userremember_user"),
        nullable=False
    )

    name = db.Column(db.String(150), nullable=False)

    date = db.Column(db.Date, nullable=False)

    remember_type = db.Column(
        db.String(50),
        nullable=False,
        default="personal"
    )

    is_recurring = db.Column(
        db.Boolean,
        default=False
    )

    is_active = db.Column(
        db.Boolean,
        default=True
    )

    is_public = db.Column(
    db.Boolean,
    nullable=False,
    default=False
)

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc)
    )

    user = db.relationship(
        "User",
        backref=db.backref(
            "user_remembers",
            lazy=True,
            cascade="all, delete-orphan"
        )
    )


# =========================
# 📧 EMAIL VERIFICATION
# =========================
class EmailVerification(db.Model):
    __tablename__ = "email_verifications"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", name="fk_emailverification_user"),
        nullable=False,
        index=True
    )

    # Store HASHED OTP, never the raw code
    code_hash = db.Column(db.String(255), nullable=False)

    expires_at = db.Column(db.DateTime, nullable=False)

    attempts = db.Column(db.Integer, nullable=False, default=0)
    max_attempts = db.Column(db.Integer, nullable=False, default=5)

    is_used = db.Column(db.Boolean, nullable=False, default=False)
    verified_at = db.Column(db.DateTime)

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc)
    )

    user = db.relationship(
        "User",
        backref=db.backref(
            "email_verifications",
            lazy=True,
            cascade="all, delete-orphan"
        )
    )

    def is_expired(self):
        return datetime.utcnow() > self.expires_at

    def __repr__(self):
        return f"<EmailVerification user_id={self.user_id}>"



# =================================
# 🔔 NOTIFICATIONS
# =================================
class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            name="fk_notification_user"
        ),
        nullable=False,
        index=True
    )

    org_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "organizations.id",
            name="fk_notification_org"
        ),
        nullable=False,
        index=True
    )

    title = db.Column(
        db.String(255),
        nullable=False
    )

    message = db.Column(
        db.Text,
        nullable=False
    )

    notification_type = db.Column(
        db.String(50),
        nullable=False,
        default="system"
    )

    related_url = db.Column(
        db.String(255)
    )

    is_read = db.Column(
        db.Boolean,
        nullable=False,
        default=False
    )

    read_at = db.Column(
        db.DateTime
    )

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    user = db.relationship(
        "User",
        backref=db.backref(
            "notifications",
            lazy=True,
            cascade="all, delete-orphan"
        )
    )

    organization = db.relationship(
        "Organization",
        backref=db.backref(
            "notifications",
            lazy=True
        )
    )

    context = db.Column(
        db.String(30),
        nullable=False,
        default="user"
    )

    remember_id = db.Column(
        db.Integer,
        db.ForeignKey("remembers.id"),
        nullable=True,
        index=True
    )

    event_id = db.Column(
        db.Integer,
        db.ForeignKey("events.id"),
        nullable=True,
        index=True
    )

    occurrence_date = db.Column(
        db.Date,
        nullable=True
    )

    __table_args__ = (
        db.Index(
            "idx_notification_user_read",
            "user_id",
            "is_read"
        ),
        db.Index(
            "idx_notification_user_created",
            "user_id",
            "created_at"
        ),
    )


# =========================
# 🔗 INVITE
# =========================
class OrgInvite(db.Model):
    __tablename__ = "org_invites"

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("organizations.id", name="fk_org_orginvite"), nullable=False)
    invite_code = db.Column(db.String(100), unique=True, nullable=False, default=lambda: secrets.token_urlsafe(6))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime)

# =========================
# 🎉 EVENT
# =========================
class Event(db.Model):
    __tablename__ = "events"

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("organizations.id", name="fk_event_org"), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    event_type = db.Column(db.String(50), default="checkin", nullable=False)  # checkin, announcement, system

    # TRIGGER
    trigger_type = db.Column(db.String(50), default="date")  # date, recurring, user
    trigger_date = db.Column(db.Date)
    frequency = db.Column(db.String(50), default="weekly")  # daily, weekly, etc.

    # AUDIENCE
    audience_type = db.Column(db.String(50), default="all")  # all, filtered
    audience_filters = db.Column(db.Text)  # JSON string later

    # DELIVERY
    delivery_channels = db.Column(db.String(100))  # "email,push"
    is_active = db.Column(db.Boolean, default=True)
    system_event_key = db.Column(db.String(50), default="birthday")  # "birthday", "anniversary", "inactivity"
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # RELATIONSHIPS
    templates = db.relationship("MessageTemplate", backref="event", lazy=True, cascade="all, delete-orphan")
    #responses = db.relationship("EventResponse", backref="event", lazy=True)
    responses = db.relationship("EventResponse", back_populates="event", lazy=True)
    questions = db.relationship("Question", backref="event", lazy=True, cascade="all, delete-orphan")

    __table_args__ = (
    db.Index('idx_event_org', 'org_id'),
    db.Index('idx_event_active', 'is_active'),
    db.Index('idx_event_trigger', 'trigger_type'),
    db.Index('idx_event_system_key', 'system_event_key')
)


# =========================
# QUESTIONS
# =========================
class Question(db.Model):
    __tablename__ = "questions"

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("organizations.id", name="fk_question_org"), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id", name="fk_question_event"), nullable=False)
    question_text = db.Column(db.String(255))
    question_type = db.Column(db.String(50))  # rating, text, etc.
    order = db.Column(db.Integer, default=0)
    depends_on_question_id = db.Column(db.Integer, db.ForeignKey("questions.id", name="fk_question_depends"), nullable=True)
    depends_on_value = db.Column(db.String(100), nullable=True)
    question_key = db.Column(db.String(100))  # e.g. mood_check, support_check
    #responses = db.relationship("EventResponse", backref="question", lazy=True)
    responses = db.relationship("EventResponse", back_populates="question", lazy=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


# =========================
# QUESTION OPTIONS (for dropdown, checkboxes, etc.)
# =========================
class QuestionOption(db.Model):
    __tablename__ = "question_options"
    
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id", name="fk_option_question"), nullable=False)
    option_text = db.Column(db.String(200), nullable=False)
    value = db.Column(db.String(100), nullable=False)        # slug-like value
    order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationship
    question = db.relationship("Question", backref=db.backref("options", lazy=True, order_by="QuestionOption.order"))


# =========================
# RESPONSE
# =========================
class EventResponse(db.Model):
    __tablename__ = "responses"
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", name="fk_response_user"), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id", name="fk_response_event"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id", name="fk_response_question"), nullable=False)
    
    answer = db.Column(db.Text)
    submitted_for_date = db.Column(db.Date, default=lambda: date.today())
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    is_system_generated = True
    response_type = "birthday"

    __table_args__ = (
        db.UniqueConstraint('user_id', 'event_id', 'question_id', 'submitted_for_date', name='uq_daily_response'),
    )

    # === RELATIONSHIPS ===
    # Use back_populates instead of backref to avoid conflicts
    user = db.relationship("User", back_populates="responses", lazy=True)
    event = db.relationship("Event", back_populates="responses", lazy=True)
    question = db.relationship("Question", back_populates="responses", lazy=True)


# =========================
# 💬 MESSAGE TEMPLATE
# =========================
class MessageTemplate(db.Model):
    __tablename__ = "message_templates"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    org_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "organizations.id",
            name="fk_mestemplate_org"
        ),
        nullable=False
    )

    # Event-based template
    event_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "events.id",
            name="fk_mestemplate_event"
        ),
        nullable=True
    )

    # Remember-based template
    remember_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "remembers.id",
            name="fk_mestemplate_remember"
        ),
        nullable=True
    )

    subject = db.Column(
        db.String(255)
    )

    body_template = db.Column(
        db.Text
    )

    channel = db.Column(
        db.String(50),
        nullable=False,
        default="email"
    )

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc)
    )

    # Only define the Remember relationship here.
    # Event already defines the relationship using
    # backref="event".
    remember = db.relationship(
        "Remember",
        backref="message_templates"
    )

    __table_args__ = (

        db.UniqueConstraint(
            "event_id",
            "channel",
            name="uq_event_template_channel"
        ),

        db.UniqueConstraint(
            "remember_id",
            "channel",
            name="uq_remember_template_channel"
        ),

        db.CheckConstraint(
            """
            (event_id IS NOT NULL AND remember_id IS NULL)
            OR
            (event_id IS NULL AND remember_id IS NOT NULL)
            """,
            name="ck_template_one_source"
        ),
    )

# =========================
# 📤 MESSAGE LOG
# =========================
class MessageLog(db.Model):
    __tablename__ = "message_logs"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            name="fk_meslog_user"
        ),
        nullable=False
    )

    org_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "organizations.id",
            name="fk_meslog_org"
        ),
        nullable=False
    )

    # Can belong to an Event OR a Remember
    event_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "events.id",
            name="fk_meslog_event"
        ),
        nullable=True
    )

    remember_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "remembers.id",
            name="fk_meslog_remember"
        ),
        nullable=True
    )

    template_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "message_templates.id",
            name="fk_meslog_template"
        ),
        nullable=True
    )

    # The actual message that was sent
    message_content = db.Column(
        db.Text
    )

    subject = db.Column(
        db.String(255)
    )

    channel = db.Column(
        db.String(50),
        nullable=False,
        default="email"
    )

    status = db.Column(
        db.String(50),
        nullable=False,
        default="sent"
    )

    # Important for recurring Remembers
    occurrence_date = db.Column(
        db.Date,
        nullable=True
    )

    sent_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc)
    )

    opened_at = db.Column(
        db.DateTime
    )

    # Relationships
    event = db.relationship(
        "Event",
        backref="message_logs"
    )

    remember = db.relationship(
        "Remember",
        backref="message_logs"
    )

    template = db.relationship(
        "MessageTemplate"
    )

    __table_args__ = (

        db.Index(
            "idx_message_user",
            "user_id"
        ),

        db.Index(
            "idx_message_event",
            "event_id"
        ),

        db.Index(
            "idx_message_remember",
            "remember_id"
        ),

        # Prevent duplicate Remember messages
        # for the same user/date/channel
        db.UniqueConstraint(
            "user_id",
            "remember_id",
            "occurrence_date",
            "channel",
            name="uq_remember_message_occurrence"
        ),

        # Prevent duplicate Event messages
        db.UniqueConstraint(
            "user_id",
            "event_id",
            "occurrence_date",
            "channel",
            name="uq_event_message_occurrence"
        ),

        # Exactly one source
        db.CheckConstraint(
            """
            (event_id IS NOT NULL AND remember_id IS NULL)
            OR
            (event_id IS NULL AND remember_id IS NOT NULL)
            """,
            name="ck_log_one_source"
        ),
    )

    def __repr__(self):
        return f"<MessageLog {self.id}>"

