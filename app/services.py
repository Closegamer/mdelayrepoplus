from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Message

OK_TEXT = "Я в порядке"
SENT_TEXT = "SENT"
ESCALATED_TEXT = "ESCALATED"


def create_message(
    db: Session,
    user_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
    message_text: str,
) -> Message:
    obj = Message(
        userid=user_id,
        username=username,
        firstname=first_name,
        lastname=last_name,
        message=message_text,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def list_user_messages(db: Session, user_id: int) -> list[Message]:
    return db.query(Message).filter(Message.userid == user_id).order_by(Message.id.desc()).all()


def delete_user_message(db: Session, user_id: int, message_id: int) -> bool:
    deleted = db.query(Message).filter(Message.id == message_id, Message.userid == user_id).delete()
    db.commit()
    return deleted > 0


def submit_response(db: Session, user_id: int, response_text: str) -> Message | None:
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
    answer = response_text.strip()
    is_ok = answer in (OK_TEXT, f"{OK_TEXT}.", OK_TEXT.lower(), f"{OK_TEXT.lower()}.")
    value = OK_TEXT if is_ok else answer
    if pending.check1_res == SENT_TEXT:
        pending.check1_res = value
        pending.check1_is_text = True
    elif pending.check2_res == SENT_TEXT:
        pending.check2_res = value
        pending.check2_is_text = True
    elif pending.check3_res == SENT_TEXT:
        pending.check3_res = value
        pending.check3_is_text = True
    if not is_ok:
        pending.check3_res = ESCALATED_TEXT
        pending.check3_is_text = False
    db.commit()
    db.refresh(pending)
    return pending


def get_active_check_for_user(db: Session, user_id: int) -> dict | None:
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
    if pending.check1_res == SENT_TEXT:
        check_no = 1
        deadline = settings.check2_seconds
    elif pending.check2_res == SENT_TEXT:
        check_no = 2
        deadline = settings.check3_seconds
    else:
        check_no = 3
        deadline = settings.check3_seconds
    return {
        "message_id": pending.id,
        "check_no": check_no,
        "source_message": pending.message,
        "response_deadline_seconds": deadline,
    }


def _dt_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _is_finished(row: Message) -> bool:
    if row.check3_res == ESCALATED_TEXT:
        return True
    return row.check1_res == OK_TEXT or row.check2_res == OK_TEXT or row.check3_res == OK_TEXT


def worker_step(
    db: Session,
    on_send_check: Callable[[Message, int], bool] | None = None,
    on_send_escalation: Callable[[Message], bool] | None = None,
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
            if (now - created_at).total_seconds() >= settings.check1_seconds:
                if on_send_check and not on_send_check(row, 1):
                    continue
                row.check1_time = now
                row.check1_res = SENT_TEXT
                row.check1_is_text = False
                continue
        if row.check1_res == SENT_TEXT and row.check2_time is None and check1_at is not None:
            if (now - check1_at).total_seconds() >= settings.check2_seconds:
                if on_send_check and not on_send_check(row, 2):
                    continue
                row.check2_time = now
                row.check2_res = SENT_TEXT
                row.check2_is_text = False
                continue
        if row.check2_res == SENT_TEXT and row.check3_time is None and check2_at is not None:
            if (now - check2_at).total_seconds() >= settings.check3_seconds:
                if on_send_check and not on_send_check(row, 3):
                    continue
                row.check3_time = now
                row.check3_res = SENT_TEXT
                row.check3_is_text = False
                continue
        if row.check3_res == SENT_TEXT and check3_at is not None:
            if (now - check3_at).total_seconds() >= settings.check3_seconds:
                if on_send_escalation and not on_send_escalation(row):
                    continue
                row.check3_res = ESCALATED_TEXT
                row.check3_is_text = False
    db.commit()
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Message

OK_TEXT = "Я в порядке"
SENT_TEXT = "SENT"
ESCALATED_TEXT = "ESCALATED"


def create_message(
    db: Session,
    user_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
    message_text: str,
) -> Message:
    obj = Message(
        userid=user_id,
        username=username,
        firstname=first_name,
        lastname=last_name,
        message=message_text,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def list_user_messages(db: Session, user_id: int) -> list[Message]:
    return db.query(Message).filter(Message.userid == user_id).order_by(Message.id.desc()).all()


def delete_user_message(db: Session, user_id: int, message_id: int) -> bool:
    deleted = db.query(Message).filter(Message.id == message_id, Message.userid == user_id).delete()
    db.commit()
    return deleted > 0


def submit_response(db: Session, user_id: int, response_text: str) -> Message | None:
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
    answer = response_text.strip()
    is_ok = answer in (OK_TEXT, f"{OK_TEXT}.", OK_TEXT.lower(), f"{OK_TEXT.lower()}.")
    value = OK_TEXT if is_ok else answer
    if pending.check1_res == SENT_TEXT:
        pending.check1_res = value
        pending.check1_is_text = True
    elif pending.check2_res == SENT_TEXT:
        pending.check2_res = value
        pending.check2_is_text = True
    elif pending.check3_res == SENT_TEXT:
        pending.check3_res = value
        pending.check3_is_text = True
    if not is_ok:
        pending.check3_res = ESCALATED_TEXT
        pending.check3_is_text = False
    db.commit()
    db.refresh(pending)
    return pending


def get_active_check_for_user(db: Session, user_id: int) -> dict | None:
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
    if pending.check1_res == SENT_TEXT:
        check_no = 1
        deadline = settings.check2_seconds
    elif pending.check2_res == SENT_TEXT:
        check_no = 2
        deadline = settings.check3_seconds
    else:
        check_no = 3
        deadline = settings.check3_seconds
    return {
        "message_id": pending.id,
        "check_no": check_no,
        "source_message": pending.message,
        "response_deadline_seconds": deadline,
    }


def _dt_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _is_finished(row: Message) -> bool:
    if row.check3_res == ESCALATED_TEXT:
        return True
    return row.check1_res == OK_TEXT or row.check2_res == OK_TEXT or row.check3_res == OK_TEXT


def worker_step(db: Session) -> None:
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
            if (now - created_at).total_seconds() >= settings.check1_seconds:
                row.check1_time = now
                row.check1_res = SENT_TEXT
                row.check1_is_text = False
                continue
        if row.check1_res == SENT_TEXT and row.check2_time is None and check1_at is not None:
            if (now - check1_at).total_seconds() >= settings.check2_seconds:
                row.check2_time = now
                row.check2_res = SENT_TEXT
                row.check2_is_text = False
                continue
        if row.check2_res == SENT_TEXT and row.check3_time is None and check2_at is not None:
            if (now - check2_at).total_seconds() >= settings.check3_seconds:
                row.check3_time = now
                row.check3_res = SENT_TEXT
                row.check3_is_text = False
                continue
        if row.check3_res == SENT_TEXT and check3_at is not None:
            if (now - check3_at).total_seconds() >= settings.check3_seconds:
                row.check3_res = ESCALATED_TEXT
                row.check3_is_text = False
    db.commit()
from sqlalchemy.orm import Session

from app.models import Message


def create_message(
    db: Session,
    user_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
    message_text: str,
) -> Message:
    obj = Message(
        userid=user_id,
        username=username,
        firstname=first_name,
        lastname=last_name,
        message=message_text,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def list_user_messages(db: Session, user_id: int) -> list[Message]:
    return db.query(Message).filter(Message.userid == user_id).order_by(Message.id.desc()).all()


def delete_user_message(db: Session, user_id: int, message_id: int) -> bool:
    deleted = db.query(Message).filter(Message.id == message_id, Message.userid == user_id).delete()
    db.commit()
    return deleted > 0


def submit_response(db: Session, user_id: int, response_text: str) -> Message | None:
    pending = (
        db.query(Message)
        .filter(
            Message.userid == user_id,
            Message.check1_time.is_not(None),
            (
                (Message.check1_res == "SENT")
                | (Message.check2_res == "SENT")
                | (Message.check3_res == "SENT")
            ),
        )
        .order_by(Message.id.desc())
        .first()
    )
    if not pending:
        return None

    answer = response_text.strip()
    is_ok = answer in ("Я в порядке", "Я в порядке.")
    value = "Я в порядке" if is_ok else answer

    if pending.check1_res == "SENT":
        pending.check1_res = value
        pending.check1_is_text = True
    elif pending.check2_res == "SENT":
        pending.check2_res = value
        pending.check2_is_text = True
    elif pending.check3_res == "SENT":
        pending.check3_res = value
        pending.check3_is_text = True

    if not is_ok:
        pending.check3_res = "ESCALATED"
        pending.check3_is_text = False

    db.commit()
    db.refresh(pending)
    return pending


def get_active_check_for_user(db: Session, user_id: int) -> dict | None:
    pending = (
        db.query(Message)
        .filter(
            Message.userid == user_id,
            Message.check1_time.is_not(None),
            (
                (Message.check1_res == "SENT")
                | (Message.check2_res == "SENT")
                | (Message.check3_res == "SENT")
            ),
        )
        .order_by(Message.id.desc())
        .first()
    )
    if not pending:
        return None

    if pending.check1_res == "SENT":
        check_no = 1
    elif pending.check2_res == "SENT":
        check_no = 2
    else:
        check_no = 3

    return {
        "message_id": pending.id,
        "check_no": check_no,
        "source_message": pending.message,
        "response_deadline_seconds": 60,
    }
