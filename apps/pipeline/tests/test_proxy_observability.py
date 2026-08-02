from serious_shift_pipeline.core.redaction import redact_secrets
from serious_shift_pipeline.steps.scraper.runner import Log


def test_proxy_credentials_are_redacted_without_hiding_host():
    message = "proxy failed: http://user:super-secret@proxy.example:8080/path"
    safe = redact_secrets(message)
    assert "user" not in safe
    assert "super-secret" not in safe
    assert "proxy.example:8080/path" in safe
    assert "[credentials]" in safe


def test_source_and_proxy_metrics_include_no_proxy_url(monkeypatch):
    monkeypatch.setenv("YOUTUBE_PROXY_COST_USD_PER_REQUEST", "0.0025")
    log = Log()
    log.proxy_request()
    log.proxy_request()
    log.source_result(
        thinker="Canary",
        platform="youtube",
        status="ok",
        item_count=3,
        duration_seconds=1.23456,
        proxied=True,
    )

    assert log.proxy_requests == 2
    assert log.proxy_cost_usd == 0.005
    assert log.source_results == [{
        "thinker": "Canary",
        "platform": "youtube",
        "status": "ok",
        "item_count": 3,
        "duration_seconds": 1.235,
        "proxied": True,
    }]
    assert "proxy_url" not in log.source_results[0]
