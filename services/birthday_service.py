from extensions import db
from datetime import date
from models import User, Event, EventResponse


# BORTHDAY AUTOMATION PROCESS
def process_birthday_events(org_id):
    today = date.today()

    # 1. Get birthday events
    birthday_events = Event.query.filter_by(
        org_id=org_id,
        system_event_key="birthday",
        is_active=True
    ).all()

    if not birthday_events:
        return []

    # 2. Get users with birthday today
    users = User.query.filter(
        db.extract("month", User.date_of_birth) == today.month,
        db.extract("day", User.date_of_birth) == today.day
    ).all()

    triggered = []

    # 3. For each event → for each user
    for event in birthday_events:
        for user in users:

            # prevent duplicates
            exists = EventResponse.query.filter_by(
                event_id=event.id,
                user_id=user.id,
                submitted_for_date=today
            ).first()

            if exists:
                continue

            response = EventResponse(
                event_id=event.id,
                user_id=user.id,
                answer="Happy Birthday 🎉",
                submitted_for_date=today,
                is_system_generated=True,
                response_type="birthday"
            )

            db.session.add(response)
            triggered.append((event.id, user.id))

    db.session.commit()

    return triggered