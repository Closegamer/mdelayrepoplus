import logging
import time
from html import escape
import requests

from app.config import settings
from app.db import Base, SessionLocal, engine
from app.services import worker_step

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

def _send_telegram_message(chat_id: int | str, text: str) -> bool:
    if not settings.bot_token:
        logger.warning("BOT_TOKEN is not set, skip telegram send")
        return False
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{settings.bot_token}/sendMessage",
            data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
        return response.ok and response.json().get("ok") is True
    except Exception:
        logger.exception("Telegram send failed")
        return False

def _send_check(row, check_no: int) -> bool:
    source_message = escape(row.message or "")
    text = (
        f"Проверка {check_no}/3.\n\n"
        "<b>Как у Вас дела?</b>\n\n"
        "Если всё хорошо, напишите фразу \"Я в порядке\"\n\n"
        "Если у Вас проблема, но Вы можете ответить, - опишите проблему текстом.\n\n"
        f"Ваше исходное сообщение:\n{source_message}"
    )
    return _send_telegram_message(row.userid, text)

def _send_escalation(row) -> bool:
    if not settings.alert_chat_id:
        logger.warning("ALERT_CHAT_ID is not set, skip escalation")
        return False
    username_text = f"@{escape(row.username)}" if row.username else "-"
    source_message = escape(row.message or "")
    text = (
        "АВАРИЙНОЕ СООБЩЕНИЕ\n\n"
        f"ID сообщения: {row.id}\n"
        f"User id: {row.userid}\n"
        f"Username: {username_text}\n\n"
        f"Текст сообщения:\n{source_message}"
    )
    return _send_telegram_message(settings.alert_chat_id, text)

def run_once() -> None:
    db = SessionLocal()
    try:
        worker_step(db, on_send_check=_send_check, on_send_escalation=_send_escalation)
    finally:
        db.close()

def main() -> None:
    Base.metadata.create_all(bind=engine)
    logger.info("Cron worker started with poll interval %ss", settings.scheduler_poll_seconds)
    while True:
        try:
            run_once()
        except Exception:
            logger.exception("Cron iteration failed")
        time.sleep(settings.scheduler_poll_seconds)

if __name__ == "__main__":
    main()
