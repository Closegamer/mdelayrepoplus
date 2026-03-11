from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.db import Base, SessionLocal, engine
from app.models import Message
from app.schemas import ActiveCheckOut, HealthOut, MessageCreate, MessageOut, MessageResponseIn

app = FastAPI(title="mDelayPlusBot API", version="0.1.0")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)

@app.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut(status="ok")

def _to_out(item: Message) -> MessageOut:
    return MessageOut(
        id=item.id,
        user_id=item.userid,
        username=item.username,
        first_name=item.firstname,
        last_name=item.lastname,
        message=item.message,
        timecreated=item.timecreated,
        check1_time=item.check1_time,
        check1_res=item.check1_res,
        check1_is_text=item.check1_is_text,
        check2_time=item.check2_time,
        check2_res=item.check2_res,
        check2_is_text=item.check2_is_text,
        check3_time=item.check3_time,
        check3_res=item.check3_res,
        check3_is_text=item.check3_is_text,
    )

@app.post("/api/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
def create_message_endpoint(payload: MessageCreate, db: Session = Depends(get_db)) -> MessageOut:
    obj = Message(
        userid=payload.user_id,
        username=payload.username,
        firstname=payload.first_name,
        lastname=payload.last_name,
        message=payload.message,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return _to_out(obj)

@app.get("/api/messages", response_model=list[MessageOut])
def list_messages_endpoint(user_id: int = Query(...), db: Session = Depends(get_db)) -> list[MessageOut]:
    rows = db.query(Message).filter(Message.userid == user_id).order_by(Message.id.desc()).all()
    return [_to_out(item) for item in rows]

@app.delete("/api/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_message_endpoint(
    message_id: int,
    user_id: int = Query(...),
    db: Session = Depends(get_db),
) -> None:
    deleted = db.query(Message).filter(Message.id == message_id, Message.userid == user_id).delete()
    db.commit()
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Message not found")

@app.post("/api/messages/response", response_model=MessageOut)
def respond_endpoint(payload: MessageResponseIn, db: Session = Depends(get_db)) -> MessageOut:
    pending = (
        db.query(Message)
        .filter(
            Message.userid == payload.user_id,
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
        raise HTTPException(status_code=404, detail="No active check for this user")

    answer = payload.response_text.strip()
    is_ok = answer in ("Я в порядке", "Я в порядке.", "я в порядке", "я в порядке.")
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
    return _to_out(pending)
    
@app.get("/api/users/{user_id}/active-check", response_model=ActiveCheckOut)
def active_check_endpoint(user_id: int, db: Session = Depends(get_db)) -> ActiveCheckOut:
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
        raise HTTPException(status_code=404, detail="No active check")

    if pending.check1_res == "SENT":
        check_no = 1
    elif pending.check2_res == "SENT":
        check_no = 2
    else:
        check_no = 3

    return ActiveCheckOut(
        message_id=pending.id,
        check_no=check_no,
        source_message=pending.message,
        response_deadline_seconds=60,
    )
