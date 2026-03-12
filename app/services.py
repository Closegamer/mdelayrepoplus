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
