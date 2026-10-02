from datetime import datetime,timezone
import pandas as pd
from active_paper_signals import opening_signals, opening_features


def sample(symbol="AAPL"):
    times=pd.date_range("2026-10-02T13:30:00Z",periods=8,freq="min")
    return pd.DataFrame(dict(symbol=symbol,timestamp=times,open=100.,high=101.,low=99.,
                             close=[100.]*5+[102.,102.,103.],volume=1000.))


def test_incomplete_current_minute_cannot_change_signal():
    data=sample()
    history={"AAPL":dict(volume=1000,dollars=100000000)}
    now=datetime(2026,10,2,13,36,tzinfo=timezone.utc)
    first=opening_signals({"AAPL":data},history,now)
    changed=data.copy()
    changed.loc[6:,"close"]=10000
    second=opening_signals({"AAPL":changed},history,now)
    first["AAPL"].pop("at");second["AAPL"].pop("at")
    assert first==second
    assert first["AAPL"]["stop_price"]==99
    assert first["AAPL"]["feed"]=="iex"


def test_no_buy_before_completed_opening_or_after_deadline():
    history={"AAPL":dict(volume=1000,dollars=100000000)}
    for hour,minute in [(13,34),(15,0)]:
        assert not opening_signals({"AAPL":sample()},history,datetime(2026,10,2,hour,minute,tzinfo=timezone.utc))


def test_missing_history_prevents_entry():
    assert not opening_signals({"AAPL":sample()},{},datetime(2026,10,2,13,36,tzinfo=timezone.utc))
    assert opening_features(sample(),["2026-10-01"]*20) is None
