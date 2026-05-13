"""MCP stdio server exposing exactly ONE tool: send_email.

Run directly with: python -m mcp_server.email_server
The client (src/mcp_client.py) spawns this as a subprocess and talks to it
over stdio.

Guardrail: only `send_email` is registered. No filesystem listing, no shell,
no other capabilities. The attachment path must resolve under PROJECT_ROOT.
"""
import smtplib
import ssl
import uuid
from email.message import EmailMessage
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from src.config import (
    PROJECT_ROOT,
    SMTP_APP_PASSWORD,
    SMTP_FROM_NAME,
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
)

mcp = FastMCP("resume-email-server")


def _validate_attachment(attachment_path: str) -> Path:
    p = Path(attachment_path).resolve()
    if not p.exists() or not p.is_file():
        raise ValueError(f"attachment not found: {p}")
    try:
        p.relative_to(PROJECT_ROOT.resolve())
    except ValueError as e:
        raise ValueError(
            f"attachment must be inside project dir {PROJECT_ROOT}"
        ) from e
    if p.suffix.lower() != ".pdf":
        raise ValueError("attachment must be a .pdf file")
    return p


@mcp.tool()
def send_email(
    to: str,
    subject: str,
    body: str,
    attachment_path: str,
) -> dict:
    """Send an email with a PDF attachment via Outlook SMTP.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Plain-text email body.
        attachment_path: Absolute path to a PDF inside the project directory.

    Returns:
        {"status": "sent", "message_id": <id>, "to": <to>}
    """
    if not SMTP_USER or not SMTP_APP_PASSWORD:
        raise RuntimeError(
            "SMTP_USER and SMTP_APP_PASSWORD must be set in .env"
        )

    pdf = _validate_attachment(attachment_path)

    msg = EmailMessage()
    msg["Subject"] = subject
    from_header = f"{SMTP_FROM_NAME} <{SMTP_USER}>" if SMTP_FROM_NAME else SMTP_USER
    msg["From"] = from_header
    msg["To"] = to
    message_id = f"<{uuid.uuid4()}@{SMTP_USER.split('@')[-1]}>"
    msg["Message-ID"] = message_id
    msg.set_content(body)

    with open(pdf, "rb") as f:
        msg.add_attachment(
            f.read(),
            maintype="application",
            subtype="pdf",
            filename=pdf.name,
        )

    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls(context=context)
        smtp.ehlo()
        smtp.login(SMTP_USER, SMTP_APP_PASSWORD)
        smtp.send_message(msg)

    return {"status": "sent", "message_id": message_id, "to": to}


if __name__ == "__main__":
    mcp.run()
