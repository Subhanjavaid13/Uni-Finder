"""Sends the report by SMTP (works with Gmail app passwords, Outlook, Brevo, etc.)."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from .config import env


class EmailError(RuntimeError):
    pass


REQUIRED = ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_TO")


def missing_email_settings() -> list[str]:
    return [name for name in REQUIRED if not env(name)]


def send_email(subject: str, html_body: str, text_body: str) -> None:
    missing = missing_email_settings()
    if missing:
        raise EmailError("Email is not configured. Missing: " + ", ".join(missing)
                         + " (set them in .env or as GitHub secrets)")

    host, port = env("SMTP_HOST"), int(env("SMTP_PORT", "587"))
    user, password = env("SMTP_USER"), env("SMTP_PASSWORD")
    recipients = [a.strip() for a in env("EMAIL_TO").split(",") if a.strip()]

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = env("EMAIL_FROM", user)
    msg["To"] = ", ".join(recipients)
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    context = ssl.create_default_context()
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=context, timeout=60) as server:
                server.login(user, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=60) as server:
                server.starttls(context=context)
                server.login(user, password)
                server.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        raise EmailError(f"Could not send email via {host}:{port}: {exc}") from exc
