import json
import pytest
from finbert_headline_inference import text_digest,verify_probability,checked_batch,news_texts,PROTOCOL


def test_text_hash_is_deterministic_sensitive_and_utf8():
    assert text_digest('Profit €')==text_digest('Profit €')
    assert text_digest('Profit €')!=text_digest('Loss €')
    assert not PROTOCOL['sentiment_is_profit_probability'] and not PROTOCOL['orders']


@pytest.mark.parametrize('values',[[1,1,1],[float('nan'),0,1],[-.1,.5,.6],[0,1]])
def test_invalid_sentiment_probabilities_rejected(values):
    with pytest.raises(ValueError): verify_probability(values)


def test_checkpoint_requires_exact_keys_runtime_model_and_source_context(tmp_path):
    p=tmp_path/'batch.json';context={'revision':'pinned','source':'fixed'}
    p.write_text(json.dumps(dict(context=context,scores={'a':[.2,.3,.5]})))
    assert checked_batch(p,['a'],context)['a']==[.2,.3,.5]
    with pytest.raises(ValueError): checked_batch(p,['b'],context)
    with pytest.raises(ValueError): checked_batch(p,['a'],{'revision':'other'})


def test_incomplete_news_archive_is_not_scored(tmp_path):
    (tmp_path/'manifest.json').write_text(json.dumps(dict(status='running')))
    with pytest.raises(ValueError,match='Complete'): news_texts(tmp_path)
