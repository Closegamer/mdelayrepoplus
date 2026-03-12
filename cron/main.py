import logging
import time

from app.config import settings
from app.db import Base, SessionLocal, engine

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def run_once() -> None:
    db = SessionLocal()
    try:
        # TODO: scheduler logic will be added in next steps.
        _ = db
    finally:
        db.close()


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
