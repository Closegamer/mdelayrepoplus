import os

class Settings:
    postgres_db: str = os.getenv("POSTGRES_DB", "kakdelatorbot")
    postgres_user: str = os.getenv("POSTGRES_USER", "kakdelatoruser")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "")
    postgres_host: str = os.getenv("POSTGRES_HOST", "db")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    bot_token: str = os.getenv("BOT_TOKEN", "")
    alert_chat_id: str = os.getenv("ALERT_CHAT_ID", "")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "")
    scheduler_poll_seconds: int = int(os.getenv("SCHEDULER_POLL_SECONDS", "60"))
    check1_seconds: int = int(os.getenv("CHECK1_SECONDS", "3600"))
    check2_seconds: int = int(os.getenv("CHECK2_SECONDS", "3600"))
    check3_seconds: int = int(os.getenv("CHECK3_SECONDS", "3600"))

settings = Settings()
