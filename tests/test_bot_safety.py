import pytest

from bot import build_broker


def test_live_trading_is_locked_without_explicit_confirmation(monkeypatch):
    monkeypatch.delenv("AUTOTRADER_LIVE_CONFIRM", raising=False)
    with pytest.raises(RuntimeError, match="Live trading is locked"):
        build_broker({"mode": "live", "market": "stock"})
