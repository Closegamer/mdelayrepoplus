from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.db import Base, SessionLocal, engine
from app.models import Message
from app.schemas import ActiveCheckOut, AdminOverviewOut, HealthOut, MessageCreate, MessageOut, MessageResponseIn
from app.services import (
    create_message,
    delete_user_message,
    get_active_check_for_user,
    get_admin_overview,
    list_active_checks,
    list_alert_messages,
    list_recent_messages,
    list_user_messages,
    submit_response,
)

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
    obj = create_message(
        db=db,
        user_id=payload.user_id,
        username=payload.username,
        first_name=payload.first_name,
        last_name=payload.last_name,
        message_text=payload.message,
    )
    return _to_out(obj)

@app.get("/api/messages", response_model=list[MessageOut])
def list_messages_endpoint(user_id: int = Query(...), db: Session = Depends(get_db)) -> list[MessageOut]:
    rows = list_user_messages(db, user_id)
    return [_to_out(item) for item in rows]

@app.delete("/api/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_message_endpoint(
    message_id: int,
    user_id: int = Query(...),
    db: Session = Depends(get_db),
) -> None:
    if not delete_user_message(db, user_id=user_id, message_id=message_id):
        raise HTTPException(status_code=404, detail="Message not found")

@app.post("/api/messages/response", response_model=MessageOut)
def respond_endpoint(payload: MessageResponseIn, db: Session = Depends(get_db)) -> MessageOut:
    pending = submit_response(db, user_id=payload.user_id, response_text=payload.response_text)
    if not pending:
        raise HTTPException(status_code=404, detail="No active check for this user")
    return _to_out(pending)

@app.get("/api/users/{user_id}/active-check", response_model=ActiveCheckOut)
def active_check_endpoint(user_id: int, db: Session = Depends(get_db)) -> ActiveCheckOut:
    active = get_active_check_for_user(db, user_id)
    if not active:
        raise HTTPException(status_code=404, detail="No active check")
    return ActiveCheckOut(**active)

@app.get("/api/admin/overview", response_model=AdminOverviewOut)
def admin_overview_endpoint(db: Session = Depends(get_db)) -> AdminOverviewOut:
    return AdminOverviewOut(**get_admin_overview(db))

@app.get("/api/admin/messages", response_model=list[MessageOut])
def admin_messages_endpoint(
    limit: int = Query(24, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[MessageOut]:
    rows = list_recent_messages(db, limit=limit, offset=offset)
    return [_to_out(item) for item in rows]

@app.get("/api/admin/alerts", response_model=list[MessageOut])
def admin_alerts_endpoint(
    limit: int = Query(24, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[MessageOut]:
    rows = list_alert_messages(db, limit=limit, offset=offset)
    return [_to_out(item) for item in rows]

@app.get("/api/admin/active-checks", response_model=list[MessageOut])
def admin_active_checks_endpoint(
    limit: int = Query(24, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[MessageOut]:
    rows = list_active_checks(db, limit=limit, offset=offset)
    return [_to_out(item) for item in rows]
