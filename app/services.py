from datetime import datetime, timezone
import re
from typing import Any, Callable
import requests
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session
from app.config import settings
from app.models import Feedback, Message

OK_TEXT = "Я в порядке"
OK_NORMALIZED_VARIANTS = {"я в порядке", "я впорядке", "явпорядке"}
SENT_TEXT = "SENT"
ESCALATED_TEXT = "ESCALATED"
LATIN_TO_CYRILLIC_SIMILAR = str.maketrans(
    {
        "a": "а",
        "e": "е",
        "o": "о",
        "p": "р",
        "c": "с",
        "y": "у",
        "x": "х",
        "k": "к",
        "m": "м",
        "t": "т",
        "b": "в",
        "h": "н",
    }
)

CheckSender = Callable[[Message, int], bool]
EscalationSender = Callable[[Message], bool]

# Нормализация текста для сравнения фразы подтверждения
def _normalize_ok_text(value: str) -> str:
    lowered = value.strip().lower().replace("ё", "е")
    lowered = lowered.translate(LATIN_TO_CYRILLIC_SIMILAR)
    lowered = re.sub(r"\s+", " ", lowered)
    lowered = lowered.strip(" .,!?:;\"'`~+-=_()[]{}<>")
    # Убираем эмодзи и прочие символы, чтобы не было ложных эскалаций
    lowered = re.sub(r"[^a-zа-я0-9\s]", "", lowered)
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered.strip()

# Проверка, что ответ эквивалентен фразе Я в порядке
def _is_ok_response(value: str) -> bool:
    normalized = _normalize_ok_text(value)
    if normalized in OK_NORMALIZED_VARIANTS:
        return True
    if normalized.startswith("я в порядке"):
        return True
    compacted = normalized.replace(" ", "")
    return compacted in OK_NORMALIZED_VARIANTS


def _active_check_no_and_deadline_seconds(pending: Message) -> tuple[int, int] | None:
    if pending.check3_res == SENT_TEXT:
        return 3, int(pending.check3_delay_seconds or 0)
    if pending.check2_res == SENT_TEXT:
        return 2, int(pending.check3_delay_seconds or 0)
    if pending.check1_res == SENT_TEXT:
        return 1, int(pending.check2_delay_seconds or 0)
    return None


def _active_check_time(pending: Message, check_no: int) -> datetime | None:
    if check_no == 3:
        return _dt_aware(pending.check3_time)
    if check_no == 2:
        return _dt_aware(pending.check2_time)
    if check_no == 1:
        return _dt_aware(pending.check1_time)
    return None


def _latest_active_pending_within_deadline(db: Session, user_id: int) -> tuple[Message, int, int] | None:
    pending = (
        db.query(Message)
        .filter(
            Message.userid == user_id,
            Message.check1_time.is_not(None),
            ((Message.check1_res == SENT_TEXT) | (Message.check2_res == SENT_TEXT) | (Message.check3_res == SENT_TEXT)),
        )
        .order_by(Message.id.desc())
        .first()
    )
    if not pending:
        return None
    active_meta = _active_check_no_and_deadline_seconds(pending)
    if not active_meta:
        return None
    check_no, deadline_seconds = active_meta
    if deadline_seconds <= 0:
        return None
    check_time = _active_check_time(pending, check_no)
    if not check_time:
        return None
    now = datetime.now(timezone.utc)
    if (now - check_time).total_seconds() >= deadline_seconds:
        return None
    return pending, check_no, deadline_seconds

# Создание нового сообщения для отслеживания
def create_message(
    db: Session,
    user_id: int,
    message_text: str,
    message_mode: str | None = None,
    check1_delay_seconds: int | None = None,
    check2_delay_seconds: int | None = None,
    check3_delay_seconds: int | None = None,
) -> Message:
    obj = Message(
        userid=user_id,
        message=message_text,
        message_mode=message_mode or "Реальный",
        check1_delay_seconds=check1_delay_seconds or settings.check1_seconds,
        check2_delay_seconds=check2_delay_seconds or settings.check2_seconds,
        check3_delay_seconds=check3_delay_seconds or settings.check3_seconds,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

# Возврат сообщений пользователя в обратном порядке
def list_user_messages(db: Session, user_id: int) -> list[Message]:
    return db.query(Message).filter(Message.userid == user_id).order_by(Message.id.desc()).all()

# Удаление сообщения пользователя по идентификатору
def delete_user_message(db: Session, user_id: int, message_id: int) -> bool:
    deleted = db.query(Message).filter(Message.id == message_id, Message.userid == user_id).delete()
    db.commit()
    return deleted > 0

# Удаление сообщения по идентификатору без привязки к пользователю
def delete_message_by_id(db: Session, message_id: int) -> bool:
    deleted = db.query(Message).filter(Message.id == message_id).delete()
    db.commit()
    return deleted > 0

# Сохранение ответа пользователя в текущий активный этап проверки
def submit_response(db: Session, user_id: int, response_text: str) -> Message | None:
    active = _latest_active_pending_within_deadline(db, user_id)
    if not active:
        return None
    pending, active_check_no, _ = active
    answer = response_text.strip()
    is_ok = _is_ok_response(answer)
    value = OK_TEXT if is_ok else answer
    pending.user_response_text = answer
    if active_check_no == 1:
        pending.check1_res = value
        pending.check1_is_text = True
    elif active_check_no == 2:
        pending.check2_res = value
        pending.check2_is_text = True
    elif active_check_no == 3:
        pending.check3_res = value
        pending.check3_is_text = True
    else:
        return None
    if not is_ok:
        pending.check3_res = ESCALATED_TEXT
        pending.check3_is_text = False
    db.commit()
    db.refresh(pending)
    return pending

# Возврат данных об активной проверке пользователя
def get_active_check_for_user(db: Session, user_id: int) -> dict | None:
    active = _latest_active_pending_within_deadline(db, user_id)
    if not active:
        return None
    pending, check_no, deadline = active
    return {
        "message_id": pending.id,
        "check_no": check_no,
        "source_message": pending.message,
        "response_deadline_seconds": deadline,
    }

# Приведение времени к формату с часовым поясом
def _dt_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value

# Определение завершенности отслеживания для сообщения
def _is_finished(row: Message) -> bool:
    if row.check3_res == ESCALATED_TEXT:
        return True
    return row.check1_res == OK_TEXT or row.check2_res == OK_TEXT or row.check3_res == OK_TEXT

# Выполнение одного шага планировщика проверок
def worker_step(
    db: Session,
    on_send_check: CheckSender | None = None,
    on_send_escalation: EscalationSender | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    rows = db.query(Message).order_by(Message.id.asc()).all()
    for row in rows:
        if _is_finished(row):
            continue
        created_at = _dt_aware(row.timecreated)
        check1_at = _dt_aware(row.check1_time)
        check2_at = _dt_aware(row.check2_time)
        check3_at = _dt_aware(row.check3_time)
        if row.check1_time is None and row.check1_res is None and created_at is not None:
            if (now - created_at).total_seconds() >= row.check1_delay_seconds:
                if on_send_check and not on_send_check(row, 1):
                    continue
                row.check1_time = now
                row.check1_res = SENT_TEXT
                row.check1_is_text = False
                continue
        if row.check1_res == SENT_TEXT and row.check2_time is None and check1_at is not None:
            if (now - check1_at).total_seconds() >= row.check2_delay_seconds:
                if on_send_check and not on_send_check(row, 2):
                    continue
                row.check2_time = now
                row.check2_res = SENT_TEXT
                row.check2_is_text = False
                continue
        if row.check2_res == SENT_TEXT and row.check3_time is None and check2_at is not None:
            if (now - check2_at).total_seconds() >= row.check3_delay_seconds:
                if on_send_check and not on_send_check(row, 3):
                    continue
                row.check3_time = now
                row.check3_res = SENT_TEXT
                row.check3_is_text = False
                continue
        if row.check3_res == SENT_TEXT and check3_at is not None:
            if (now - check3_at).total_seconds() >= row.check3_delay_seconds:
                if on_send_escalation and not on_send_escalation(row):
                    continue
                row.check3_res = ESCALATED_TEXT
                row.check3_is_text = False
    db.commit()

# Формирование условия выборки активных проверок
def _active_condition():
    return and_(
        or_(Message.check3_res.is_(None), Message.check3_res != ESCALATED_TEXT),
        or_(Message.check1_res.is_(None), Message.check1_res != OK_TEXT),
        or_(Message.check2_res.is_(None), Message.check2_res != OK_TEXT),
        or_(Message.check3_res.is_(None), Message.check3_res != OK_TEXT),
    )

# Возврат последних сообщений с пагинацией
def list_recent_messages(db: Session, limit: int, offset: int) -> list[Message]:
    return db.query(Message).order_by(Message.id.desc()).offset(offset).limit(limit).all()

# Возврат тревожных сообщений с пагинацией
def list_alert_messages(db: Session, limit: int, offset: int) -> list[Message]:
    return (
        db.query(Message)
        .filter(
            Message.check3_res == ESCALATED_TEXT,
            or_(Message.check1_res.is_(None), Message.check1_res != OK_TEXT),
            or_(Message.check2_res.is_(None), Message.check2_res != OK_TEXT),
            or_(Message.check3_res.is_(None), Message.check3_res != OK_TEXT),
        )
        .order_by(Message.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

# Возврат активных проверок с пагинацией
def list_active_checks(db: Session, limit: int, offset: int) -> list[Message]:
    return (
        db.query(Message)
        .filter(_active_condition())
        .order_by(Message.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

# Создание записи обратной связи
def create_feedback(db: Session, user_id: int, message_text: str) -> Feedback:
    obj = Feedback(userid=user_id, message=message_text)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


# Возврат обратной связи с пагинацией для админки
def list_feedback(db: Session, limit: int, offset: int) -> list[Feedback]:
    return (
        db.query(Feedback)
        .order_by(Feedback.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


# Удаление записи обратной связи по идентификатору
def delete_feedback_by_id(db: Session, feedback_id: int) -> bool:
    deleted = db.query(Feedback).filter(Feedback.id == feedback_id).delete()
    db.commit()
    return deleted > 0


# Проверка доступности бота через Telegram API getMe
def get_bot_telegram_health() -> dict[str, Any]:
    token = (settings.bot_token or "").strip()
    if not token:
        return {
            "ok": False,
            "telegram_ok": False,
            "bot_username": None,
            "bot_id": None,
            "error": "BOT_TOKEN не задан",
        }
    try:
        response = requests.get(
            f"https://api.telegram.org/bot{token}/getMe",
            timeout=10,
        )
        body = response.json()
        if body.get("ok") and body.get("result"):
            result = body["result"]
            return {
                "ok": True,
                "telegram_ok": True,
                "bot_username": result.get("username"),
                "bot_id": result.get("id"),
                "error": None,
            }
        err = body.get("description") or response.text or f"HTTP {response.status_code}"
        return {
            "ok": False,
            "telegram_ok": False,
            "bot_username": None,
            "bot_id": None,
            "error": err,
        }
    except Exception as exc:
        return {
            "ok": False,
            "telegram_ok": False,
            "bot_username": None,
            "bot_id": None,
            "error": str(exc),
        }


# Возврат агрегированных метрик для админки
def get_admin_overview(db: Session) -> dict:
    total_messages = db.query(func.count(Message.id)).scalar() or 0
    total_users = db.query(func.count(func.distinct(Message.userid))).scalar() or 0
    total_alerts = db.query(func.count(Message.id)).filter(Message.check3_res == ESCALATED_TEXT).scalar() or 0
    active_checks = db.query(func.count(Message.id)).filter(_active_condition()).scalar() or 0
    # Количество отправленных проверок считаем по факту отправки (наличие времени),
    # а не по текущему статусу ответа, который может измениться позже.
    check1_sent = db.query(func.count(Message.id)).filter(Message.check1_time.is_not(None)).scalar() or 0
    check2_sent = db.query(func.count(Message.id)).filter(Message.check2_time.is_not(None)).scalar() or 0
    check3_sent = db.query(func.count(Message.id)).filter(Message.check3_time.is_not(None)).scalar() or 0
    return {
        "total_messages": int(total_messages),
        "total_users": int(total_users),
        "total_alerts": int(total_alerts),
        "active_checks": int(active_checks),
        "check1_sent": int(check1_sent),
        "check2_sent": int(check2_sent),
        "check3_sent": int(check3_sent),
    }
