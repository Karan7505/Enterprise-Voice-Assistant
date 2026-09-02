from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.core.config import settings
from app.core.database import initialize_database
from app.services.tts_service import cleanup_old_audio_files, ensure_audio_directory


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    ensure_audio_directory()
    cleanup_old_audio_files()
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
