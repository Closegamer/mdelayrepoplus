from datetime import datetime
from pydantic import BaseModel, Field

class MessageCreate(BaseModel):
    user_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    message: str = Field(min_length=1)
    message_mode: str | None = None
    check1_delay_seconds: int | None = Field(default=None, ge=60)
    check2_delay_seconds: int | None = Field(default=None, ge=60)
    check3_delay_seconds: int | None = Field(default=None, ge=60)

class MessageResponseIn(BaseModel):
    user_id: int
    response_text: str = Field(min_length=1)

class MessageOut(BaseModel):
    id: int
    user_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    message: str
    message_mode: str
    timecreated: datetime
    check1_time: datetime | None
    check1_res: str | None
    check1_is_text: bool
    check2_time: datetime | None
    check2_res: str | None
    check2_is_text: bool
    check3_time: datetime | None
    check3_res: str | None
    check3_is_text: bool
    check1_delay_seconds: int
    check2_delay_seconds: int
    check3_delay_seconds: int

class ActiveCheckOut(BaseModel):
    message_id: int
    check_no: int
    source_message: str
    response_deadline_seconds: int

class HealthOut(BaseModel):
    status: str

class AdminOverviewOut(BaseModel):
    total_messages: int
    total_users: int
    total_alerts: int
    active_checks: int
    check1_sent: int
    check2_sent: int
    check3_sent: int
