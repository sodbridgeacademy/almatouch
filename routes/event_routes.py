from flask import request, redirect, render_template, session, Blueprint, url_for, flash
from flask import request, redirect, render_template
from models import User, Organization, OrgInvite, Department, UserDepartment, Question, Event
from services.event_service import create_default_checkin_event
from datetime import datetime, timedelta
#from extensions import db, bcrypt
import uuid


# User Blueprint
event_bp = Blueprint("event", __name__)


# LOGIC
@event_bp.route("/org/events/checkin")
def org_checkin_event():

    org_id = session.get("org_id")
    if not org_id:
        return redirect(url_for("org.org_login"))

    # 🔥 AUTO-CREATE IF MISSING
    event = create_default_checkin_event(org_id)

    questions = Question.query.filter_by(
        event_id=event.id
    ).order_by(Question.order.asc()).all()

    return render_template(
        "org/checkin_event.html",
        event=event,
        questions=questions
    )


@event_bp.route("/org/events/checkin")
def org_checkin_event1st():

    org_id = session.get("org_id")
    if not org_id:
        return redirect(url_for("org.org_login"))

    event = Event.query.filter_by(
        org_id=org_id,
        event_type="checkin",
        system_event_key="wellbeing_checkin"
    ).first()

    questions = []

    if event:
        questions = Question.query.filter_by(
            event_id=event.id
        ).order_by(Question.order.asc()).all()

    return render_template(
        "org/checkin_event.html",
        event=event,
        questions=questions
    )