import logging
from contextlib import asynccontextmanager
from pathlib import Path

import certifi
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api import admin, auth, common, manager, marketer
from src.config import get_settings

load_dotenv()

LOGGER = logging.getLogger(__name__)


def validate_tls_ca_bundle() -> Path:
    ca_bundle_path = Path(certifi.where())
    if not ca_bundle_path.is_file():
        raise RuntimeError(
            f"TLS CA certificate bundle is missing: {ca_bundle_path}. "
            "Reinstall certifi in the active virtual environment."
        )
    return ca_bundle_path


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    validate_tls_ca_bundle()
    LOGGER.info("Starting %s in %s mode", settings.app_name, settings.app_env)
    yield


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Multi-agent marketing content pipeline",
    version="1.0.0",
    lifespan=lifespan,
)

# Auth uses bearer tokens rather than cookies, so credentials stay off.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

common.register_error_handlers(app)
for router_module in (auth, admin, manager, marketer):
    app.include_router(router_module.router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}
