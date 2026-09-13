import secrets
from datetime import datetime, timezone, timedelta

from extensions import db, bcrypt
from models import EmailVerification
from utils.email_sender import send_verification_email


OTP_EXPIRY_MINUTES = 10


def generate_email_otp():
    """
    Generate a secure 6-digit email verification OTP.
    """
    return f"{secrets.randbelow(1_000_000):06d}"


def create_email_verification(user):
    """
    Create a new email verification OTP for a user,
    invalidate previous unused OTPs, and send the new OTP.
    """

    # Generate raw OTP
    otp_code = generate_email_otp()

    # Invalidate previous unused verification codes
    EmailVerification.query.filter_by(
        user_id=user.id,
        is_used=False
    ).update(
        {"is_used": True},
        synchronize_session=False
    )

    # Hash OTP before storing it
    code_hash = bcrypt.generate_password_hash(
        otp_code
    ).decode("utf-8")

    # Create verification record
    verification = EmailVerification(
        user_id=user.id,
        code_hash=code_hash,
        expires_at=(
            datetime.now(timezone.utc)
            + timedelta(minutes=OTP_EXPIRY_MINUTES)
        )
    )

    db.session.add(verification)
    db.session.commit()

    # Send RAW OTP to the user's email.
    # Only the hash is stored in the database.
    send_verification_email(
        user=user,
        otp_code=otp_code
    )

    return verification