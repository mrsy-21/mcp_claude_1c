"""FastAPI application entry point for the 1C OData bridge."""

import os
from contextlib import asynccontextmanager

import httpx
import structlog
from dotenv import load_dotenv
from fastapi import FastAPI

from log_config.config import setup_logging
from api.odata_client import ODataClient, ODataError
from api.routers import metadata as metadata_router

load_dotenv()
setup_logging(os.getenv("LOG_LEVEL", "INFO"))

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    """Manage application startup and shutdown.

    On startup:
    - Creates a shared ODataClient and stores it in ``app.state``.
    - Fetches OData ``$metadata`` and caches entity list.
      If 1C is unreachable the app still starts; metadata will be ``None``
      and the /metadata endpoint will return 503 until a manual refresh.

    On shutdown:
    - Closes the httpx client cleanly.
    """
    base_url = os.environ["ODATA_BASE_URL"]
    user = os.environ["ODATA_USER"]
    password = os.environ["ODATA_PASSWORD"]

    client = ODataClient(base_url=base_url, user=user, password=password)
    fastapi_app.state.odata_client = client
    fastapi_app.state.metadata = None

    try:
        fastapi_app.state.metadata = await client.fetch_metadata()
        log.info("startup_metadata_loaded", entity_count=len(fastapi_app.state.metadata))
    except ODataError as exc:
        log.warning(
            "startup_metadata_failed",
            status_code=exc.status_code,
            detail=exc.message,
        )
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        log.warning("startup_metadata_failed", error=str(exc))

    yield

    await client.close()
    log.info("shutdown_complete")


app = FastAPI(
    title="1C OData Bridge",
    description=(
        "FastAPI middleware between the MCP server and 1C/BAS OData. "
        "Exposes semantic endpoints that map to OData entity queries."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(metadata_router.router)


@app.get("/health", tags=["system"])
async def health() -> dict:
    """Health check endpoint.

    Returns:
        ``{"status": "ok"}`` — always 200 as long as the process is alive.
        The caller should use ``GET /metadata`` to verify 1C connectivity.
    """
    return {"status": "ok"}
