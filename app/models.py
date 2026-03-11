from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Identity, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    userid: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(Text, nullable=True)
    firstname: Mapped[str | None] = mapped_column(Text, nullable=True)
    lastname: Mapped[str | None] = mapped_column(Text, nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    timecreated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    check1_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    check1_res: Mapped[str | None] = mapped_column(Text, nullable=True)
    check1_is_text: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    check2_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    check2_res: Mapped[str | None] = mapped_column(Text, nullable=True)
    check2_is_text: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    check3_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    check3_res: Mapped[str | None] = mapped_column(Text, nullable=True)
    check3_is_text: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

Index("idx_messages_userid", Message.userid)
Index("idx_messages_timecreated", Message.timecreated)
