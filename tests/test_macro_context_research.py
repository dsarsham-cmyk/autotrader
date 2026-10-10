import numpy as np
import pandas as pd
import pytest
import macro_context_research as research


def frame(date='2026-10-01',symbol='SPY'):
    times=list(pd.date_range(f'{date} 09:30',periods=35,freq='min',tz='America/New_York'))
    times.append(pd.Timestamp(f'{date} 15:59',tz='America/New_York'))
    return pd.DataFrame(dict(symbol=symbol,timestamp=[t.isoformat() for t in times],
        open=100.,high=101.,low=99.,close=100.,volume=1000.))


@pytest.mark.parametrize('date',['2026-10-01','2026-01-02'])
def test_opening_context_uses_exact_ny_cutoff_across_dst(date):
    groups=research.proxy_sessions(frame(date),'SPY')
    opening=groups[date].loc[groups[date].minute<600]
    assert len(opening)==30 and opening.minute.iloc[-1]==599


def fixture():
    dates=pd.bdate_range('2026-08-03',periods=26).strftime('%Y-%m-%d').tolist()
    observations={s:{d:research.proxy_sessions(frame(d,s),s)[d] for d in dates} for s in research.PROXIES}
    bars=np.tile([100.,101.,99.,100.,1000.],(390,1))
    equities={d:{'A':(bars.copy(),dict(prior_dollars=3e7,relative_volume=1))} for d in dates}
    return dates,observations,equities


def test_todays_future_close_or_its_absence_cannot_change_todays_features():
    dates,observations,equities=fixture();before,_=research.matched_rows(equities,observations)
    for symbol in research.PROXIES:
        regular=observations[symbol][dates[-1]]
        regular.loc[regular.minute>=600,['open','high','low','close','volume']]=[200,210,190,200,1e9]
    after,_=research.matched_rows(equities,observations)
    assert before==after
    for symbol in research.PROXIES:
        regular=observations[symbol][dates[-1]]
        observations[symbol][dates[-1]]=regular.loc[regular.minute<600].copy()
    missing,_=research.matched_rows(equities,observations)
    assert before==missing and len(before[-1]['features'])==63


def test_prior_volume_benchmark_excludes_current_opening_volume():
    date='2026-10-01';regular=research.proxy_sessions(frame(date),'SPY')[date]
    opening=regular.loc[regular.minute<600]
    prior=[dict(close=100,volume=30000) for _ in range(21)]
    values,_=research.context(opening,prior)
    assert values[5]==pytest.approx(np.log(2))
    changed=opening.copy();changed.volume*=2
    updated,_=research.context(changed,prior)
    assert updated[5]==pytest.approx(np.log(3)) and values[:5]==updated[:5]


def test_missing_proxy_keeps_ineligible_day_and_preceding_forecasts_unchanged():
    dates,observations,equities=fixture();before,_=research.matched_rows(equities,observations)
    del observations['UUP'][dates[-1]]
    after,_=research.matched_rows(equities,observations)
    assert before[:-1]==after[:-1] and len(before)==len(after)
    assert not after[-1]['predecision_eligible'] and 'UUP:missing_proxy_session' in after[-1]['eligibility_reason']


@pytest.mark.parametrize('issue',['naive','duplicate','wrong_symbol'])
def test_ambiguous_proxy_source_rejected(issue):
    source=frame()
    if issue=='naive': source.timestamp=source.timestamp.str.slice(0,19)
    if issue=='duplicate': source.loc[1,'timestamp']=source.loc[0,'timestamp']
    if issue=='wrong_symbol': source.symbol='GLD'
    with pytest.raises(ValueError): research.proxy_sessions(source,'SPY')


def test_post_cutoff_opening_input_rejected_not_used_as_recent_context():
    date='2026-10-01';regular=research.proxy_sessions(frame(date),'SPY')[date]
    with pytest.raises(ValueError,match='cutoff'):
        research.context(regular,[dict(close=100,volume=30000)]*21)
