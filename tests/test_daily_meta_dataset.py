import pandas as pd
import pytest
from daily_meta_dataset import combine_frames


def frame(day='2024-01-02T14:30:00Z',close=100):
    return pd.DataFrame([dict(symbol='AAPL',timestamp=day,open=100,high=101,low=99,close=close,volume=1000)])


def test_join_sorts_and_keeps_identical_overlap_once():
    combined=combine_frames([frame('2024-01-03T14:30:00Z'),frame(),frame()],'AAPL')
    assert len(combined)==2 and str(combined.timestamp.iloc[0]).startswith('2024-01-02')


def test_conflicting_revision_cannot_silently_replace_old_data():
    with pytest.raises(ValueError,match='Conflicting'):
        combine_frames([frame(),frame(close=100.5)],'AAPL')


def test_symbol_and_schema_mismatch_rejected():
    wrong=frame();wrong['symbol']='MSFT'
    with pytest.raises(ValueError,match='symbol'): combine_frames([frame(),wrong],'AAPL')
    with pytest.raises(ValueError,match='schema'): combine_frames([frame(),frame().drop(columns=['volume'])],'AAPL')
