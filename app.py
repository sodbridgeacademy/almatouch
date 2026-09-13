from flask import Flask, render_template
from flask_migrate import Migrate
from extensions import db, bcrypt, login_manager, mail
from dotenv import load_dotenv
from scheduler import start_scheduler
from datetime import timezone
from zoneinfo import ZoneInfo
import os
from models import User


app = Flask(__name__)
load_dotenv()


# =========================
# CONFIG
# =========================
#app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///almatouch.db'
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['SECRET_KEY'] = os.getenv(
    "SECRET_KEY",
    "dev-secret-key"
)

# # =========================
# # EMAIL CONFIGURATION
# # =========================
# app.config['MAIL_SERVER'] = 'smtp.gmail.com'
# app.config['MAIL_PORT'] = 587
# app.config['MAIL_USE_TLS'] = True
# #app.config['MAIL_USERNAME'] = 'sodbridgeacademy@gmail.com'
# #app.config['MAIL_PASSWORD'] = 'iwac sqpd logx vbsw'
# app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
# app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
# app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')

# =========================
# INIT EXTENSIONS
# =========================
#login_manager.login_view = "login"

db.init_app(app)
bcrypt.init_app(app)
login_manager.init_app(app)
#mail.init_app(app)

migrate = Migrate(app, db)

# =========================
# IMPORT ROUTES (AFTER app creation)
# =========================
from routes.org_routes import org_bp
from routes.user_routes import user_bp
from routes.dept_routes import dept_bp
from routes.event_routes import event_bp

# test
@app.route("/test-email")
def test_email():
    from utils.email_sender import send_email

    send_email(
        to="dpsalmist546@gmail.com",
        subject="Alma Touch Moment",
        body="This is a test email from Alma Touch app using the OS Env."
    )

    return "Test email sent."

app.register_blueprint(org_bp)
app.register_blueprint(user_bp)
app.register_blueprint(dept_bp)
app.register_blueprint(event_bp)


# =========================
# HOME ROUTE
# =========================
@app.route("/")
def home():
    return render_template("index.html")
    #return "Almatouch is running 🚀"


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.context_processor
def inject_notification_count():

    from models import Notification, User
    from flask import session

    user_id = session.get("user_id")

    if not user_id:
        return {
            "unread_notification_count": 0
        }

    user = User.query.get(user_id)

    if not user or not user.is_active:
        return {
            "unread_notification_count": 0
        }

    count = Notification.query.filter_by(
        user_id=user.id,
        org_id=user.org_id,
        context="user",
        is_read=False
    ).count()

    return {
        "unread_notification_count": count
    }


@app.context_processor
def inject_org_notification_count():

    from models import Notification, User
    from flask import session

    user_id = session.get("user_id")

    if not user_id:
        return {
            "unread_org_notification_count": 0
        }

    user = User.query.get(user_id)

    if not user or not user.is_active:
        return {
            "unread_org_notification_count": 0
        }

    if user.role not in ["owner", "admin"]:
        return {
            "unread_org_notification_count": 0
        }

    count = Notification.query.filter_by(
        user_id=user.id,
        org_id=user.org_id,
        context="organization",
        is_read=False
    ).count()

    return {
        "unread_org_notification_count": count
    }
   

@app.template_filter("localtime")
def localtime(value, tz_name="Africa/Lagos", fmt="%b %d, %Y · %I:%M %p"):
    if not value:
        return ""

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    return value.astimezone(ZoneInfo(tz_name)).strftime(fmt)



@app.route("/test-smtp")
def test_smtp():
    import smtplib
    import os

    try:
        with smtplib.SMTP(
            os.getenv("MAIL_SERVER", "smtp.gmail.com"),
            int(os.getenv("MAIL_PORT", 587)),
            timeout=10
        ) as server:

            server.starttls()

            server.login(
                os.getenv("MAIL_USERNAME"),
                os.getenv("MAIL_PASSWORD")
            )

        return "SMTP connection and authentication successful."

    except Exception as e:
        return f"SMTP ERROR: {type(e).__name__}: {str(e)}", 500


# =========================
# START APP
# =========================
# if __name__ == "__main__":
#     with app.app_context():
#         db.create_all()

#     # Start scheduler
#     start_scheduler()

#     app.run(
#         debug=True,
#         use_reloader=False
#     )

if __name__ == "__main__":
    start_scheduler()

    app.run(
        debug=True,
        use_reloader=False
    )

