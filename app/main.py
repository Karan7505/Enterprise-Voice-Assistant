import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.core import logging_conf
from app.core.config import settings
from app.core.correlation import CorrelationIDMiddleware
from app.core.database import close_pool, initialize_database
from app.core.redis_client import close_redis, ping_redis
from app.services.tts_service import cleanup_old_audio_files, ensure_audio_directory

# Configure structured logging before any other import emits a record.
logging_conf.setup_logging()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # The async routes offload blocking DB/Redis work to the anyio thread
    # pool; raise its default (40) so 50-user load keeps ample headroom
    # without queueing on pool acquisition.
    from anyio.to_thread import current_default_thread_limiter

    current_default_thread_limiter().total_tokens = 128

    initialize_database()
    if ping_redis():
        logger.info("Redis session/rate-limit store reachable")
    else:
        # The process still starts (health checks, /status work), but every
        # authenticated request fails closed until Redis is reachable.
        logger.warning(
            "Redis is unreachable at startup; authentication will fail "
            "closed until it is available"
        )
    ensure_audio_directory()
    cleanup_old_audio_files()
    yield
    close_redis()
    close_pool()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Added last -> outermost: every request (including CORS/security handling)
# gets a correlation id and a structured access log line.
app.add_middleware(CorrelationIDMiddleware)


# Security headers on every API response. The SPA's Content-Security-Policy is
# enforced at the reverse proxy in production (see README "Security notes");
# these protect the API surface itself.
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


app.include_router(auth_router)
app.include_router(chat_router)
