from copy import deepcopy
import pytest
from news_event_features import index_news,features,add_news,FEATURES


def article(i=1,created='2026-10-12T13:30:00Z',updated='2026-10-12T13:30:01Z'):
    return dict(id=i,created_at=created,updated_at=updated,headline='Earnings beats forecast',symbols=['A'])


def test_future_article_and_future_revision_text_never_backdated():
    old=article();late=article(2,updated='2026-10-12T14:01:00Z')
    baseline=features(index_news([old],['A']),'A','2026-10-12')
    assert features(index_news([old,late],['A']),'A','2026-10-12')==baseline
    late['headline']='Profit forecast cuts loss falls'
    assert features(index_news([old,late],['A']),'A','2026-10-12')==baseline


def test_cutoff_exclusive_and_updated_version_not_original_creation():
    item=article(updated='2026-10-12T14:00:00Z')
    assert features(index_news([item],['A']),'A','2026-10-12')==[0.]*len(FEATURES)


def test_versions_older_than_24h_do_not_enter_features():
    item=article(created='2026-10-10T13:00:00Z',updated='2026-10-10T13:30:00Z')
    assert features(index_news([item],['A']),'A','2026-10-12')==[0.]*len(FEATURES)


def test_ny_cutoff_adjusts_for_winter_dst():
    item=article(created='2026-12-01T14:30:00Z',updated='2026-12-01T14:30:01Z')
    f=features(index_news([item],['A']),'A','2026-12-01')
    assert f[0]>0 and f[1]>0


def test_missing_news_does_not_remove_stock_or_rewrite_base_features():
    rows=[dict(date='2026-10-12',symbol='A',features=[1],signal_price=100)]
    result=add_news(rows,index_news([],['A']))
    assert len(result)==1 and result[0]['features']==[1]+[0.]*len(FEATURES)
    assert rows[0]['features']==[1]


def test_duplicate_and_reversed_timestamps_rejected():
    with pytest.raises(ValueError,match='Duplicate'): index_news([article(),article()],['A'])
    with pytest.raises(ValueError,match='before creation'):
        index_news([article(created='2026-10-12T13:40:00Z')],['A'])
