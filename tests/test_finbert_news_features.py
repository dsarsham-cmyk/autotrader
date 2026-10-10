import pytest
from finbert_headline_inference import text_digest
from finbert_news_features import index_scores,sentiment_features,add_sentiment,FEATURES


def item(i=1,updated='2026-10-12T13:30:00Z',headline='Earnings'):
    return dict(id=i,headline=headline,created_at='2026-10-12T13:00:00Z',updated_at=updated,symbols=['A'])


def test_future_revision_sentiment_never_backdated():
    scores={text_digest('Earnings'):[.9,.05,.05],text_digest('Future'):[.05,.9,.05]}
    before=sentiment_features(index_scores([item()],scores,['A']),'A','2026-10-12')
    after=sentiment_features(index_scores([item(),item(2,'2026-10-12T14:01:00Z','Future')],scores,['A']),'A','2026-10-12')
    assert before==after and before[:3]==[.9,.05,.05]


def test_cutoff_exclusive_and_no_news_retains_stock():
    index=index_scores([item(updated='2026-10-12T14:00:00Z')],{text_digest('Earnings'):[.9,.05,.05]},['A'])
    rows=[dict(date='2026-10-12',symbol='A',features=[1])]
    assert add_sentiment(rows,index)[0]['features']==[1]+[0.]*len(FEATURES)
    assert rows[0]['features']==[1]


def test_missing_sentiment_score_is_error_not_neutral_fill():
    with pytest.raises(KeyError): index_scores([item()],{},['A'])


def test_signed_dispersion_is_descriptive_not_profit_probability():
    articles=[item(),item(2,headline='Other')]
    scores={text_digest('Earnings'):[.8,.1,.1],text_digest('Other'):[.1,.8,.1]}
    result=sentiment_features(index_scores(articles,scores,['A']),'A','2026-10-12')
    assert result[-1]==pytest.approx(.7)
    assert result[:3]==pytest.approx([.45,.45,.1])


def test_complete_cache_binds_exact_news_model_source_and_every_headline(tmp_path):
    import hashlib,json
    from pathlib import Path
    from finbert_headline_inference import PROTOCOL,WEIGHT_SHA
    from finbert_news_features import load_scores
    news=tmp_path/'news.json';news.write_bytes(b'fixture archive manifest')
    article=item();scores={text_digest(article['headline']):[.8,.1,.1]}
    context=dict(protocol=PROTOCOL,news_manifest_sha256=hashlib.sha256(news.read_bytes()).hexdigest(),
        model_files={'pytorch_model.bin':WEIGHT_SHA},
        source_sha256=hashlib.sha256(Path('finbert_headline_inference.py').read_bytes().replace(b'\r\n',b'\n')).hexdigest())
    report=dict(status='completed_private_finbert_sentiment_only',context=context,
        completed_headlines=1,scores=scores)
    cache=tmp_path/'cache.json';cache.write_text(json.dumps(report))
    assert load_scores(cache,news,[article])[0]==scores
    report['completed_headlines']=0;cache.write_text(json.dumps(report))
    with pytest.raises(ValueError,match='Missing'): load_scores(cache,news,[article])
    report['completed_headlines']=1;report['context']['model_files']['pytorch_model.bin']='other'
    cache.write_text(json.dumps(report))
    with pytest.raises(ValueError,match='Unpinned'): load_scores(cache,news,[article])


def test_partial_inference_cache_never_used_for_trading_features(tmp_path):
    import json
    from finbert_news_features import load_scores
    cache=tmp_path/'cache.json';cache.write_text(json.dumps(dict(status='running_private_finbert_sentiment_only')))
    with pytest.raises(ValueError,match='Completed'): load_scores(cache,tmp_path/'absent',[item()])
