from risk import RiskConfig, RiskManager


def test_daily_loss_uses_previous_close_and_resets_next_day():
    manager = RiskManager(RiskConfig(daily_loss_limit_pct=0.02))
    manager.update_equity(97_500, "2026-09-17", day_start_equity=100_000)
    assert manager.halted
    assert manager.halt_reason == "daily loss limit"

    manager.update_equity(97_500, "2026-09-18", day_start_equity=97_500)
    assert not manager.halted


def test_account_loss_budget_survives_fresh_manager():
    manager = RiskManager(RiskConfig(
        starting_equity=100_000,
        max_account_loss_pct=0.10,
        max_drawdown_pct=0.50,
    ))
    manager.update_equity(89_999, "2026-09-17", day_start_equity=90_000)
    assert manager.halted
    assert manager.halt_reason == "account loss budget"


def test_risk_state_round_trip():
    original = RiskManager(RiskConfig())
    original.update_equity(101_000, "2026-09-17", day_start_equity=100_000)
    restored = RiskManager(RiskConfig())
    restored.restore(original.snapshot())
    assert restored.peak_equity == 101_000
    assert restored.day_start_equity == 100_000
    assert restored.current_day == "2026-09-17"
