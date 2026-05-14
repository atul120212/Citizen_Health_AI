"""Async appointment confirmation email via SMTP.

Uses stdlib smtplib in a thread-pool executor so the FastAPI event loop is
never blocked.  If SMTP_USER / SMTP_PASSWORD are not set the email is printed
to stdout (demo / dev mode) so the rest of the flow can be tested without a
real mail server.
"""

import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from ..config import get_settings

logger = logging.getLogger(__name__)

# ── Multilingual email templates ───────────────────────────────────────────────

_SUBJECTS: dict[str, str] = {
    "ta-IN": "உங்கள் Appointment உறுதிப்படுத்தல் — Citizen Health AI",
    "kn-IN": "ನಿಮ್ಮ Appointment ದೃಢೀಕರಣ — Citizen Health AI",
    "hi-IN": "आपका Appointment Confirmation — Citizen Health AI",
    "en-IN": "Your Appointment Confirmation — Citizen Health AI",
}

_BODY_TEMPLATES: dict[str, str] = {
    "ta-IN": """\
வணக்கம் {name},

உங்கள் appointment வெற்றிகரமாக பதிவு செய்யப்பட்டது.

  நோக்கம்  : {reason}
  தேதி      : {date}
  நேரம்     : {time}
  PHC       : {phc}

ஏதேனும் மாற்றம் தேவைப்பட்டால், உங்கள் PHC-யை தொடர்பு கொள்ளவும்.

நன்றி,
Citizen Health AI
""",
    "kn-IN": """\
ನಮಸ್ಕಾರ {name},

ನಿಮ್ಮ appointment ಯಶಸ್ವಿಯಾಗಿ ನೋಂದಾಯಿಸಲಾಗಿದೆ.

  ಕಾರಣ    : {reason}
  ದಿನಾಂಕ   : {date}
  ಸಮಯ     : {time}
  PHC      : {phc}

ಯಾವುದೇ ಬದಲಾವಣೆಗಳಿಗೆ ನಿಮ್ಮ PHC ಅನ್ನು ಸಂಪರ್ಕಿಸಿ.

ಧನ್ಯವಾದಗಳು,
Citizen Health AI
""",
    "hi-IN": """\
नमस्ते {name},

आपका appointment सफलतापूर्वक book हो गया है।

  कारण   : {reason}
  तारीख  : {date}
  समय    : {time}
  PHC    : {phc}

किसी भी बदलाव के लिए अपने PHC से संपर्क करें।

धन्यवाद,
Citizen Health AI
""",
    "en-IN": """\
Hello {name},

Your appointment has been successfully booked.

  Reason : {reason}
  Date   : {date}
  Time   : {time}
  PHC    : {phc}

To make any changes, please contact your PHC.

Thank you,
Citizen Health AI
""",
}


def _build_message(
    to_email: str,
    patient_name: str,
    reason: str,
    date: str,
    time: str,
    phc: str,
    language_code: str,
) -> MIMEMultipart:
    lang = language_code if language_code in _SUBJECTS else "en-IN"
    subject = _SUBJECTS[lang]
    body = _BODY_TEMPLATES[lang].format(
        name=patient_name, reason=reason, date=date, time=time, phc=phc
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = get_settings().smtp_from
    msg["To"] = to_email
    msg.attach(MIMEText(body, "plain", "utf-8"))
    return msg


def _send_sync(msg: MIMEMultipart, to_email: str) -> None:
    settings = get_settings()
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
        server.ehlo()
        server.starttls()
        server.login(settings.smtp_user, settings.smtp_password)  # type: ignore[arg-type]
        server.sendmail(settings.smtp_from, [to_email], msg.as_string())


async def send_appointment_confirmation(
    *,
    to_email: str,
    patient_name: str,
    reason: str,
    date: str,
    time: str,
    phc: str = "Your PHC",
    language_code: str = "en-IN",
) -> bool:
    """Send confirmation email.  Returns True on success, False on failure.

    Falls back to demo mode (stdout log) when SMTP credentials are absent.
    """
    settings = get_settings()
    msg = _build_message(to_email, patient_name, reason, date, time, phc, language_code)

    if not settings.smtp_user or not settings.smtp_password:
        # Demo mode — just log so devs can verify the content
        logger.info(
            "[EMAIL DEMO] To: %s | Subject: %s\n%s",
            to_email,
            msg["Subject"],
            msg.get_payload(0).get_payload(decode=True).decode("utf-8"),  # type: ignore[union-attr]
        )
        return True

    try:
        await asyncio.to_thread(_send_sync, msg, to_email)
        logger.info("[EMAIL] Confirmation sent to %s", to_email)
        return True
    except Exception as exc:
        logger.error("[EMAIL] Failed to send to %s: %s", to_email, exc)
        return False
