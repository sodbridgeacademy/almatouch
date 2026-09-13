from flask import current_app
from flask_mail import Message
from extensions import mail

import os
import resend
from resend.exceptions import ResendError


os.getenv("RESEND_API_KEY")


# def send_email(to, subject, body, html=None):
#     """
#     Send an email through the configured mail provider.
#     """

#     msg = Message(
#         subject=subject,
#         recipients=[to],
#         sender=current_app.config["MAIL_DEFAULT_SENDER"]
#     )

#     msg.body = body

#     if html:
#         msg.html = html

#     mail.send(msg)


def send_email(to, subject, body=None, html=None):
    params = {
        "from": "Alma Touch <noreply@damsloop.com>",
        "to": [to],
        "subject": subject,
        "html": html or f"<p>{body}</p>"
    }

    resend.Emails.send(params)


def send_verification_email(user, otp_code):
    """
    Send the email verification OTP to a user.
    """

    subject = "Verify your Alma Touch email"

    body = f"""
Hello {user.first_name},

Welcome to Alma Touch.

Your email verification code is:

{otp_code}

This code expires in 10 minutes.

If you did not create an Alma Touch account, you can safely ignore this email.

Alma Touch
Remember. Recognize. Care.
"""

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Verify your Alma Touch email</title>
</head>

<body style="font-family: Arial, sans-serif; line-height: 1.6;">

    <h2>Welcome to Alma Touch 👋</h2>

    <p>Hello {user.first_name},</p>

    <p>
        Welcome to Alma Touch. Please use the verification code below
        to verify your email address and continue your onboarding.
    </p>

    <div style="
        font-size: 32px;
        font-weight: bold;
        letter-spacing: 8px;
        margin: 25px 0;
    ">
        {otp_code}
    </div>

    <p>
        This code expires in <strong>10 minutes</strong>.
    </p>

    <p>
        If you did not create an Alma Touch account, you can safely
        ignore this email.
    </p>

    <p>
        <strong>Alma Touch</strong><br>
        Remember. Recognize. Care.
    </p>

</body>
</html>
"""

    send_email(
        to=user.email,
        subject=subject,
        body=body,
        html=html
    )


