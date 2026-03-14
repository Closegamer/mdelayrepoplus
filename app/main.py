from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db import Base, SessionLocal, engine
from app.models import Message
from app.schemas import (
    ActiveCheckOut,
    AdminOverviewOut,
    HealthOut,
    MessageCreate,
    MessageOut,
    MessageResponseIn,
    UserContactOut,
    UserContactUpsertIn,
)
from app.services import (
    create_message,
    delete_message_by_id,
    delete_user_message,
    get_user_contact,
    get_active_check_for_user,
    get_admin_overview,
    list_active_checks,
    list_alert_messages,
    list_recent_messages,
    list_user_messages,
    submit_response,
    upsert_user_contact,
)

app = FastAPI(title="mDelayPlusBot API", version="0.1.0")

# Открытие и закрытие сессии БД для запроса
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.on_event("startup")

# Создание таблиц и добавление недостающих колонок
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS message_mode TEXT NOT NULL DEFAULT 'Реальный'"))
        conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS check1_delay_seconds INTEGER NOT NULL DEFAULT 3600"))
        conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS check2_delay_seconds INTEGER NOT NULL DEFAULT 3600"))
        conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS check3_delay_seconds INTEGER NOT NULL DEFAULT 3600"))
        conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS user_response_text TEXT"))

@app.get("/health", response_model=HealthOut)

# Возврат статуса здоровья сервиса
def health() -> HealthOut:
    return HealthOut(status="ok")

# Преобразование ORM объекта сообщения в схему API
def _to_out(item: Message) -> MessageOut:
    return MessageOut(
        id=item.id,
        user_id=item.userid,
        username=item.username,
        first_name=item.firstname,
        last_name=item.lastname,
        message=item.message,
        message_mode=item.message_mode,
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
        user_response_text=item.user_response_text,
        check1_delay_seconds=item.check1_delay_seconds,
        check2_delay_seconds=item.check2_delay_seconds,
        check3_delay_seconds=item.check3_delay_seconds,
    )

@app.post("/api/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED)

# Создание новой записи сообщения для слежения
def create_message_endpoint(payload: MessageCreate, db: Session = Depends(get_db)) -> MessageOut:
    obj = create_message(
        db=db,
        user_id=payload.user_id,
        username=payload.username,
        first_name=payload.first_name,
        last_name=payload.last_name,
        message_text=payload.message,
        message_mode=payload.message_mode,
        check1_delay_seconds=payload.check1_delay_seconds,
        check2_delay_seconds=payload.check2_delay_seconds,
        check3_delay_seconds=payload.check3_delay_seconds,
    )
    return _to_out(obj)

@app.get("/api/messages", response_model=list[MessageOut])

# Возврат всех сообщений конкретного пользователя
def list_messages_endpoint(user_id: int = Query(...), db: Session = Depends(get_db)) -> list[MessageOut]:
    rows = list_user_messages(db, user_id)
    return [_to_out(item) for item in rows]

@app.delete("/api/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)

# Удаление сообщения пользователя по идентификатору
def delete_message_endpoint(
    message_id: int,
    user_id: int = Query(...),
    db: Session = Depends(get_db),
) -> None:
    if not delete_user_message(db, user_id=user_id, message_id=message_id):
        raise HTTPException(status_code=404, detail="Message not found")

@app.post("/api/messages/response", response_model=MessageOut)

# Сохранение ответа пользователя на активную проверку
def respond_endpoint(payload: MessageResponseIn, db: Session = Depends(get_db)) -> MessageOut:
    pending = submit_response(db, user_id=payload.user_id, response_text=payload.response_text)
    if not pending:
        raise HTTPException(status_code=404, detail="No active check for this user")
    return _to_out(pending)

# Преобразование контакта пользователя в схему API
def _contact_to_out(item) -> UserContactOut:
    return UserContactOut(
        user_id=item.userid,
        contact_text=item.contact_text,
        username=item.username,
        first_name=item.firstname,
        last_name=item.lastname,
    )

@app.post("/api/users/{user_id}/contact", response_model=UserContactOut)
# Сохранение контакта близкого человека для пользователя
def upsert_user_contact_endpoint(
    user_id: int,
    payload: UserContactUpsertIn,
    db: Session = Depends(get_db),
) -> UserContactOut:
    obj = upsert_user_contact(
        db=db,
        user_id=user_id,
        contact_text=payload.contact_text,
        username=payload.username,
        first_name=payload.first_name,
        last_name=payload.last_name,
    )
    return _contact_to_out(obj)

@app.get("/api/users/{user_id}/contact", response_model=UserContactOut)
# Получение контакта близкого человека для пользователя
def get_user_contact_endpoint(user_id: int, db: Session = Depends(get_db)) -> UserContactOut:
    obj = get_user_contact(db=db, user_id=user_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Contact not found")
    return _contact_to_out(obj)

@app.get("/api/users/{user_id}/active-check", response_model=ActiveCheckOut)

# Возврат текущей активной проверки пользователя
def active_check_endpoint(user_id: int, db: Session = Depends(get_db)) -> ActiveCheckOut:
    active = get_active_check_for_user(db, user_id)
    if not active:
        raise HTTPException(status_code=404, detail="No active check")
    return ActiveCheckOut(**active)

@app.get("/api/admin/overview", response_model=AdminOverviewOut)

# Возврат агрегированных показателей для админки
def admin_overview_endpoint(db: Session = Depends(get_db)) -> AdminOverviewOut:
    return AdminOverviewOut(**get_admin_overview(db))

@app.get("/api/admin/messages", response_model=list[MessageOut])

# Возврат последних сообщений с пагинацией для админки
def admin_messages_endpoint(
    limit: int = Query(24, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[MessageOut]:
    rows = list_recent_messages(db, limit=limit, offset=offset)
    return [_to_out(item) for item in rows]

@app.delete("/api/admin/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)

# Удаление сообщения из админки
def admin_delete_message_endpoint(message_id: int, db: Session = Depends(get_db)) -> None:
    if not delete_message_by_id(db, message_id=message_id):
        raise HTTPException(status_code=404, detail="Message not found")

@app.get("/api/admin/alerts", response_model=list[MessageOut])

# Возврат тревожных сообщений с пагинацией
def admin_alerts_endpoint(
    limit: int = Query(24, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[MessageOut]:
    rows = list_alert_messages(db, limit=limit, offset=offset)
    return [_to_out(item) for item in rows]

@app.get("/api/admin/active-checks", response_model=list[MessageOut])

# Возврат активных проверок с пагинацией
def admin_active_checks_endpoint(
    limit: int = Query(24, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[MessageOut]:
    rows = list_active_checks(db, limit=limit, offset=offset)
    return [_to_out(item) for item in rows]
