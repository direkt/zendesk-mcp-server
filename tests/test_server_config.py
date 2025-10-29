import logging

import pytest

from zendesk_mcp_server import server


@pytest.fixture(autouse=True)
def reset_client_cache(monkeypatch):
    # Ensure each test starts with a clean client/settings cache.
    server._reset_client_cache_for_tests()
    for key in server.REQUIRED_ENV_VARS:
        monkeypatch.delenv(key, raising=False)
    yield
    server._reset_client_cache_for_tests()
    # Clean up env vars to avoid leakage between tests.
    for key in server.REQUIRED_ENV_VARS:
        monkeypatch.delenv(key, raising=False)


def test_get_settings_returns_expected(monkeypatch):
    monkeypatch.setenv("ZENDESK_SUBDOMAIN", "demo")
    monkeypatch.setenv("ZENDESK_EMAIL", "agent@example.com")
    monkeypatch.setenv("ZENDESK_API_KEY", "token")

    settings = server.get_settings()

    assert settings["ZENDESK_SUBDOMAIN"] == "demo"
    assert settings["ZENDESK_EMAIL"] == "agent@example.com"
    assert settings["ZENDESK_API_KEY"] == "token"


def test_get_settings_raises_when_env_missing(monkeypatch):
    for key in server.REQUIRED_ENV_VARS:
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(RuntimeError) as excinfo:
        server.get_settings()

    message = str(excinfo.value).lower()
    assert "missing required environment variables" in message
    for key in server.REQUIRED_ENV_VARS:
        assert key.lower() in message


def test_configure_logging_idempotent():
    # Remove any pre-existing handlers for a clean slate.
    original_handlers = list(server.logger.handlers)
    for handler in original_handlers:
        server.logger.removeHandler(handler)

    try:
        server.configure_logging()
        first_count = len(server.logger.handlers)
        # Calling configure_logging again should not add extra handlers.
        server.configure_logging()
        second_count = len(server.logger.handlers)

        assert first_count == 1
        assert second_count == first_count
        assert isinstance(server.logger.handlers[0], logging.Handler)
    finally:
        # Restore original handlers so other modules aren't affected.
        for handler in list(server.logger.handlers):
            server.logger.removeHandler(handler)
        for handler in original_handlers:
            server.logger.addHandler(handler)
