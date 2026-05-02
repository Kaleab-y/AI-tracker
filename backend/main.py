from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from api.routes import router as api_router
from database.connection import create_db_and_tables

# Load environment variables from .env file
load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup database tables on startup
    create_db_and_tables()
    yield
    # Teardown (if necessary)


app = FastAPI(title="AI Telemetry Proxy", lifespan=lifespan)

# Register the router
app.include_router(api_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
