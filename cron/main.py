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

# Отправка сообщения в Telegram API
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

# Отправка очередного контрольного опроса пользователю
def _send_check(row, check_no: int) -> bool:
    source_message = escape(str(row.message or ""))
    text = (
        f"Проверка {check_no}/3.\n\n"
        "🔔 <b>КАК У ВАС ДЕЛА?</b>\n\n"
        "Если всё хорошо, напишите фразу \"Я в порядке\"\n\n"
        "Если у Вас проблема, но Вы можете ответить, - опишите проблему текстом.\n\n"
        f"Ваше исходное сообщение:\n{source_message}"
    )
    return _send_telegram_message(row.userid, text)

# Отправка аварийного сообщения в чат оповещений
def _send_escalation(row) -> bool:
    if not settings.alert_chat_id:
        logger.warning("ALERT_CHAT_ID is not set, skip escalation")
        return False
    created_text = escape(str(row.timecreated))
    source_message = escape(str(row.message or ""))
    is_test_mode = row.message_mode == "Тестовый" or (
        int(getattr(row, "check1_delay_seconds", 0) or 0) == 60
        and int(getattr(row, "check2_delay_seconds", 0) or 0) == 60
        and int(getattr(row, "check3_delay_seconds", 0) or 0) == 60
    )
    mode_text = "РЕЖИМ: ТЕСТОВЫЙ (все периоды по 1 минуте)\n\n" if is_test_mode else ""
    un = getattr(row, "username", None) or None
    fn = getattr(row, "firstname", None) or "-"
    ln = getattr(row, "lastname", None) or "-"
    username_line = f"Username: @{escape(un)}\n" if un else "Username: -\n"
    text = (
        "АВАРИЙНОЕ СООБЩЕНИЕ\n\n"
        f"{mode_text}"
        f"ID сообщения: {row.id}\n"
        f"User id: {row.userid}\n"
        f"{username_line}"
        f"Имя: {escape(fn)}\n"
        f"Фамилия: {escape(ln)}\n"
        f"Время создания сообщения: {created_text}\n\n"
        f"Текст сообщения:\n{source_message}"
    )
    return _send_telegram_message(settings.alert_chat_id, text)

# Выполнение одного цикла обработки проверок
def run_once() -> None:
    db = SessionLocal()
    try:
        worker_step(db, on_send_check=_send_check, on_send_escalation=_send_escalation)
    finally:
        db.close()

# Запуск бесконечного цикла cron воркера
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
