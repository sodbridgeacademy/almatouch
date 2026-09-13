from extensions import db
from models import Event, Question


# 3 DEFAULT QUESTIONS SEEDED
def create_default_checkin_event1(org_id):

    # check if already exists
    existing = Event.query.filter_by(
        org_id=org_id,
        system_event_key="wellbeing_checkin"
    ).first()

    if existing:
        return existing

    # create event
    event = Event(
        org_id=org_id,
        name="Daily Wellbeing Check-in",
        event_type="checkin",
        trigger_type="recurring",
        frequency="daily",
        system_event_key="wellbeing_checkin",
        is_active=True
    )

    db.session.add(event)
    db.session.flush()

    # DEFAULT QUESTIONS (THIS IS WHAT YOU ARE MISSING)
    questions = [
        # Q1: Mood Check
        Question(
            org_id=org_id,
            event_id=event.id,
            question_text="How are you feeling today?",
            question_type="rating",
            order=1,
            question_key="mood_check"
        ),
        # Q2: Context Check
        Question(
            org_id=org_id,
            event_id=event.id,
            question_text="Is anything affecting your work or wellbeing?",
            question_type="text",
            order=2,
            question_key="context_check"
        ),
        # Q3: Support Check
        Question(
            org_id=org_id,
            event_id=event.id,
            question_text="Do you need any support?",
            question_type="yes_no",
            order=3,
            question_key="support_check"
        ),
        # Q4: Conditional Follow Up
        Question(
        org_id=org_id,
            event_id=event.id,
            question_text="What kind of support do you need?",
            question_type="multi_choice",
            order=4,
            depends_on_question_id=support_check_id,
            depends_on_value="yes",
            question_key="support_type"
        )
    ]

    db.session.add_all(questions)
    db.session.commit()

    return event


def create_default_checkin_event111(org_id):

    existing_event = Event.query.filter_by(
        org_id=org_id,
        event_type="checkin"
    ).first()

    if existing_event:
        return existing_event


    # =====================
    # CREATE EVENT
    # =====================
    event = Event(
        org_id=org_id,
        name="Daily Wellbeing Check-in",
        event_type="checkin",
        trigger_type="recurring",
        frequency="daily",
        audience_type="all",
        is_active=True
    )

    db.session.add(event)
    db.session.flush()


    # =====================
    # QUESTION 1
    # =====================
    mood_question = Question(
        org_id=org_id,
        event_id=event.id,
        question_text="How are you feeling today?",
        question_type="mood",
        order=1,
        question_key="mood_check"
    )

    db.session.add(mood_question)
    db.session.flush()


    # =====================
    # QUESTION 2
    # =====================
    wellbeing_question = Question(
        org_id=org_id,
        event_id=event.id,
        question_text="Is anything affecting your work or wellbeing?",
        question_type="text",
        order=2,
        question_key="wellbeing_check"
    )

    db.session.add(wellbeing_question)
    db.session.flush()


    # =====================
    # QUESTION 3
    # =====================
    support_question = Question(
        org_id=org_id,
        event_id=event.id,
        question_text="Do you need any support?",
        question_type="support",
        order=3,
        question_key="support_check"
    )

    db.session.add(support_question)
    db.session.flush()


    # =====================
    # CONDITIONAL FOLLOW-UP
    # only show if support = yes
    # =====================
    follow_up_question = Question(
        org_id=org_id,
        event_id=event.id,
        question_text="What kind of support do you need?",
        question_type="support_details",
        order=4,
        depends_on_question_id=support_question.id,
        depends_on_value="yes",
        question_key="support_details"
    )

    db.session.add(follow_up_question)

    db.session.commit()

    return event


def get_mood_question_text(frequency: str) -> str:
    """Return appropriate mood question based on frequency"""
    frequency = frequency.lower()
    
    if frequency == "daily":
        return "How was your day today?"
    elif frequency in ["twice_weekly", "bi_weekly"]:
        return "How have the last few days been?"
    elif frequency == "weekly":
        return "How was your week overall?"
    elif frequency == "bi_weekly":
        return "How have the last 2 weeks been?"
    elif frequency == "monthly":
        return "How was your month overall?"
    else:
        return "How are you feeling today?"  # fallback


def create_default_checkin_event(org_id):
    existing_event = Event.query.filter_by(
        org_id=org_id,
        event_type="checkin"
    ).first()
    if existing_event:
        return existing_event

    # =====================
    # CREATE EVENT
    # =====================
    event = Event(
        org_id=org_id,
        name="Daily Wellbeing Check-in",
        event_type="checkin",
        trigger_type="recurring",
        frequency="daily",
        audience_type="all",
        is_active=True
    )
    db.session.add(event)
    db.session.flush()

    # =====================
    # QUESTION 1 - Dynamic based on frequency
    # =====================
    mood_text = get_mood_question_text(frequency)

    mood_question = Question(
        org_id=org_id,
        event_id=event.id,
        question_text=mood_text,
        question_type="mood",
        order=1,
        question_key="mood_check"
    )
    db.session.add(mood_question)
    db.session.flush()

    # =====================
    # QUESTION 1
    # =====================
    # mood_question = Question(
    #     org_id=org_id,
    #     event_id=event.id,
    #     question_text="How are you feel?",
    #     question_type="mood",
    #     order=1,
    #     question_key="mood_check"
    # )
    # db.session.add(mood_question)
    # db.session.flush()

    # =====================
    # QUESTION 2
    # =====================
    wellbeing_question = Question(
        org_id=org_id,
        event_id=event.id,
        question_text="Is anything affecting your work or wellbeing?",
        question_type="text",
        order=2,
        question_key="wellbeing_check"
    )
    db.session.add(wellbeing_question)
    db.session.flush()

    # =====================
    # QUESTION 3
    # =====================
    support_question = Question(
        org_id=org_id,
        event_id=event.id,
        question_text="Do you need any support?",
        question_type="support",
        order=3,
        question_key="support_check"
    )
    db.session.add(support_question)
    db.session.flush()

    # =====================
    # QUESTION 4 - Multi-select Support Details
    # =====================
    support_details = Question(
        org_id=org_id,
        event_id=event.id,
        question_text="What kind of support do you need? (Select all that apply)",
        question_type="multi_select",
        order=4,
        depends_on_question_id=support_question.id,
        depends_on_value="yes",
        question_key="support_details"
    )
    db.session.add(support_details)
    db.session.flush()

    # Add options for multi-select
    options_list = [
        ("Emotional support", "emotional_support"),
        ("Health / Medical", "health_medical"),
        ("Financial support", "financial_support"),
        ("Family / Relationship issues", "family_relationship"),
        ("Work-related stress", "work_stress"),
        ("Housing / Accommodation", "housing"),
        ("Other", "other")
    ]

    for i, (text, val) in enumerate(options_list):
        option = QuestionOption(
            question_id=support_details.id,
            option_text=text,
            value=val,
            order=i+1
        )
        db.session.add(option)

    db.session.commit()
    return event

# CORE CHECK-IN FETCH LOGIC
def get_active_checkin_events(org_id):

    return Event.query.filter_by(
        org_id=org_id,
        is_active=True,
        event_type="checkin"
    ).all()

# LOAD QUESTIONS FOR EVENT
def get_event_questions(event_id):

    return Question.query.filter_by(
        event_id=event_id
    ).order_by(Question.order.asc()).all()

# FILTER LOGIC
def should_show_question(question, previous_answers):

    if not question.depends_on_question_id:
        return True

    parent_answer = previous_answers.get(question.depends_on_question_id)

    return parent_answer == question.depends_on_value



# REVIEW FUNC
def create_default_checkin_event1st(org_id):

    event = Event(
        org_id=org_id,
        name="Daily Wellbeing Check-in",
        event_type="checkin",
        trigger_type="recurring",
        frequency="daily",
        audience_type="all",
        delivery_channels="push,email",
        system_event_key="wellbeing_checkin",
        is_active=True
    )

    db.session.add(event)
    db.session.flush()  # get event.id

    # default questions can also be seeded here (optional)
    return event

    # Q1: Mood Check
    Question(
        org_id=org_id,
        event_id=event.id,
        question_text="How are you feeling today?",
        question_type="rating",
        order=1,
        question_key="mood_check"
    )

    # Q2: Context Check
    Question(
        org_id=org_id,
        event_id=event.id,
        question_text="Is anything affecting your work or wellbeing?",
        question_type="text",
        order=2,
        question_key="context_check"
    )

    # Q3: Support Check
    Question(
        org_id=org_id,
        event_id=event.id,
        question_text="Do you need any support?",
        question_type="yes_no",
        order=3,
        question_key="support_check"
    )

    # Conditional Follow Up
    Question(
    org_id=org_id,
        event_id=event.id,
        question_text="What kind of support do you need?",
        question_type="multi_choice",
        order=4,
        depends_on_question_id=support_check_id,
        depends_on_value="yes",
        question_key="support_type"
    )
