import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, text

from api.routes import router as api_router
from database.connection import create_db_and_tables, engine

# Load environment variables from .env file
load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup database tables on startup
    create_db_and_tables()
    yield
    # Teardown (if necessary)


app = FastAPI(title="AI Telemetry Proxy", lifespan=lifespan)

# Allow the Next.js frontend to access the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    ).split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count", "X-Request-ID"],
)

# Register the router
app.include_router(api_router)


@app.get("/health")
def health():
    with Session(engine) as session:
        session.exec(text("SELECT 1"))
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
