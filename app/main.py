from fastapi import FastAPI
from app.db import Base, SessionLocal, engine
from app.schemas import HealthOut

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
