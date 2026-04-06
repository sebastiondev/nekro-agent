"""
PoC test: Unauthenticated webhook endpoint (CWE-862)

Demonstrates that:
1. BEFORE fix: POST /api/webhook/{endpoint} succeeds without any auth header
2. AFTER fix: POST /api/webhook/{endpoint} returns 401 without valid auth token
3. AFTER fix: POST /api/webhook/{endpoint} succeeds with valid webhook secret header
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from nekro_agent.core.exception_handlers import register_exception_handlers
from nekro_agent.routers.webhook import router

app = FastAPI()
app.include_router(router, prefix="/api")
register_exception_handlers(app)


FAKE_WEBHOOK_SECRET = "test-webhook-secret-key"
FAKE_ENDPOINT = "test-endpoint"


@pytest.fixture
def mock_plugin_collector():
    """Mock plugin_collector so there is at least one webhook method for our endpoint."""
    fake_method = AsyncMock(return_value=None)
    with patch("nekro_agent.routers.webhook.plugin_collector") as mock_collector:
        mock_collector.get_webhook_methods_by_endpoint.return_value = [
            ("fake_plugin", fake_method)
        ]
        yield mock_collector, fake_method


@pytest.fixture
def mock_agent_ctx():
    """Mock AgentCtx.create_by_webhook so it doesn't need DB/etc."""
    fake_ctx = MagicMock()
    with patch("nekro_agent.routers.webhook.AgentCtx") as mock_cls:
        mock_cls.create_by_webhook = AsyncMock(return_value=fake_ctx)
        yield mock_cls


def _has_osenv_import():
    """Check if the webhook module currently imports OsEnv (i.e. fix is applied)."""
    import nekro_agent.routers.webhook as wh
    return hasattr(wh, "OsEnv")


def _mock_osenv():
    """Return a context manager that patches OsEnv on the webhook module if it exists."""
    if _has_osenv_import():
        return patch("nekro_agent.routers.webhook.OsEnv", WEBHOOK_SECRET_KEY=FAKE_WEBHOOK_SECRET)
    # Before fix, no OsEnv — return a no-op context manager
    from contextlib import nullcontext
    return nullcontext()


@pytest.mark.asyncio
async def test_webhook_rejects_request_without_auth(
    mock_plugin_collector, mock_agent_ctx
):
    """Requests without X-Webhook-Token header should be rejected (401)."""
    payload = {"key": "value"}
    with _mock_osenv():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/webhook/{FAKE_ENDPOINT}",
                json=payload,
            )
    assert resp.status_code == 401, (
        f"Expected 401 Unauthorized but got {resp.status_code}. "
        "The webhook endpoint is accessible without authentication!"
    )


@pytest.mark.asyncio
async def test_webhook_rejects_request_with_wrong_token(
    mock_plugin_collector, mock_agent_ctx
):
    """Requests with an incorrect X-Webhook-Token should be rejected (401)."""
    payload = {"key": "value"}
    with _mock_osenv():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/webhook/{FAKE_ENDPOINT}",
                json=payload,
                headers={
                    "X-Webhook-Token": "wrong-token",
                },
            )
    assert resp.status_code == 401, (
        f"Expected 401 but got {resp.status_code}. "
        "The webhook endpoint accepted a wrong token!"
    )


@pytest.mark.asyncio
async def test_webhook_accepts_request_with_valid_token(
    mock_plugin_collector, mock_agent_ctx
):
    """Requests with the correct X-Webhook-Token should succeed (200)."""
    payload = {"key": "value"}
    with _mock_osenv():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/webhook/{FAKE_ENDPOINT}",
                json=payload,
                headers={
                    "X-Webhook-Token": FAKE_WEBHOOK_SECRET,
                },
            )
    assert resp.status_code == 200, (
        f"Expected 200 but got {resp.status_code}: {resp.text}"
    )
