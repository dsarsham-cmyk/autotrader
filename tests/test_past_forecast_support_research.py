import pytest
import math
from predictive_research import wilson
from past_forecast_support_research import support_schedule,apply_support


def daily(count=80):
    return [dict(date=f'{i:04}',active=True,pnl=1.) for i in range(count)]


def test_current_and_future_losses_cannot_revise_past_permissions():
    rows=daily();dates=[r['date'] for r in rows]
    before=support_schedule(dates,rows,.9)
    changed=[dict(r,pnl=-10000.) if i>=65 else r for i,r in enumerate(rows)]
    after=support_schedule(dates,changed,.9)
    assert before[:66]==after[:66]
    assert before[60]['trading_eligible'] and not any(s['trading_eligible'] for s in before[:60])
    assert before[65]['past_last']==dates[64]
    assert not after[66]['trading_eligible']


def test_abstention_is_not_win_or_support():
    rows=[dict(r,active=False,pnl=0.) for r in daily()]
    result=support_schedule([r['date'] for r in rows],rows,.5)
    assert all(not s['trading_eligible'] and s['past_control_winning_days']==0 and s['past_control_wilson_lower'] is None for s in result)
    rows[0]['pnl']=1
    with pytest.raises(ValueError): support_schedule([r['date'] for r in rows],rows,.5)


def test_probabilities_preserved_and_permission_completeness():
    forecasts=[dict(date='a',symbol='AAPL',probability=.95),dict(date='b',symbol='AAPL',probability=.94)]
    schedule=[dict(date='a',trading_eligible=False),dict(date='b',trading_eligible=True)]
    selected=apply_support(forecasts,schedule)
    assert [r['forecast_probability'] for r in selected]==[.95,.94]
    assert [r['probability'] for r in selected]==[0,.94]
    assert forecasts[0]['probability']==.95
    with pytest.raises(ValueError): apply_support(forecasts,schedule[:1])
    with pytest.raises(ValueError): apply_support(forecasts,schedule+schedule[:1])


def test_missing_or_reordered_control_day_rejected():
    rows=daily();dates=[r['date'] for r in rows]
    for malformed in (rows[:-1],rows[::-1],rows+rows[:1]):
        with pytest.raises(ValueError): support_schedule(dates,malformed,.65)


def test_rounded_wilson_does_not_change_any_fixed_protocol_gate():
    for n in range(20,61):
        for wins in range(n+1):
            p=wins/n;z=1.96
            lower=(p+z*z/(2*n)-z*math.sqrt(p*(1-p)/n+z*z/(4*n*n)))/(1+z*z/n)
            for gate in (.5,.65,.9):
                assert (lower>=gate)==(wilson(wins,n)[0]/100>=gate)
