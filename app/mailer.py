"""Enquiry notification e-mail over SMTP. The SMTP password is stored encrypted in the database."""
import base64
import hashlib
import logging
import os
import smtplib
import ssl
import threading
from email.message import EmailMessage
from email.utils import formataddr

from cryptography.fernet import Fernet, InvalidToken

log = logging.getLogger("sap.mail")


def _fernet(secret: str) -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))


def encrypt(secret: str, text: str) -> str:
    return _fernet(secret).encrypt(text.encode()).decode() if text else ""


def decrypt(secret: str, token: str) -> str:
    try:
        return _fernet(secret).decrypt(token.encode()).decode() if token else ""
    except InvalidToken:
        return ""


def effective(cfg: dict, secret: str) -> dict:
    """Environment variables (set in Coolify) win over what is saved in the admin panel."""
    cfg = cfg or {}
    return {
        "host": os.environ.get("SMTP_HOST") or cfg.get("host", ""),
        "port": int(os.environ.get("SMTP_PORT") or cfg.get("port") or 587),
        "user": os.environ.get("SMTP_USER") or cfg.get("user", ""),
        "password": os.environ.get("SMTP_PASSWORD") or decrypt(secret, cfg.get("password_enc", "")),
        "from_addr": os.environ.get("SMTP_FROM") or cfg.get("from_addr") or cfg.get("user", ""),
        "from_name": cfg.get("from_name") or "SAP Hardware website",
        "to": [t.strip() for t in (os.environ.get("ENQUIRY_TO") or ",".join(cfg.get("to", []))).split(",") if t.strip()],
    }


def send(conf: dict, subject: str, text: str, html: str = "", reply_to: str = "", to=None):
    """Blocking send. Raises on failure with a readable message."""
    to = to or conf["to"]
    if not conf["host"] or not conf["from_addr"]:
        raise RuntimeError("Email is not set up yet (SMTP server / sender missing).")
    if not to:
        raise RuntimeError("No recipient email address is set.")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((conf["from_name"], conf["from_addr"]))
    msg["To"] = ", ".join(to)
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    ctx = ssl.create_default_context()
    if conf["port"] == 465:
        s = smtplib.SMTP_SSL(conf["host"], conf["port"], timeout=20, context=ctx)
    else:
        s = smtplib.SMTP(conf["host"], conf["port"], timeout=20)
        s.ehlo()
        if s.has_extn("starttls"):
            s.starttls(context=ctx)
            s.ehlo()
    try:
        if conf["user"]:
            s.login(conf["user"], conf["password"])
        s.send_message(msg)
    finally:
        try:
            s.quit()
        except Exception:
            pass


def send_async(conf, subject, text, html, reply_to, on_done):
    """Fire-and-forget so the visitor never waits on the mail server; on_done(status) records the result."""
    def run():
        try:
            send(conf, subject, text, html, reply_to)
            on_done("sent")
        except Exception as e:  # pragma: no cover - network dependent
            log.warning("enquiry mail failed: %s", e)
            on_done("failed: %s" % str(e)[:180])
    threading.Thread(target=run, daemon=True).start()
