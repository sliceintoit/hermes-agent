"""Regression tests for auxiliary client cache model isolation."""

from agent.auxiliary_client import _client_cache_key


def test_client_cache_key_isolates_explicit_and_automatic_models():
    automatic = _client_cache_key("nous", async_mode=True, model=None, is_vision=True)
    explicit = _client_cache_key(
        "nous", async_mode=True, model="gpt-4o-mini", is_vision=True
    )
    recommended = _client_cache_key(
        "nous",
        async_mode=True,
        model="stepfun/step-3.7-flash:free",
        is_vision=True,
    )

    assert automatic != explicit
    assert explicit == recommended
