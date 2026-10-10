"""Past-version sentiment aggregates; sentiment is NOT profit probability."""
from bisect import bisect_left
from datetime import datetime,time,timedelta
import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo
from finbert_headline_inference import PROTOCOL,WEIGHT_SHA,text_digest,verify_probability
from prospective_forecast_evidence import timestamp

FEATURES=['mean_positive_24h','mean_negative_24h','mean_neutral_24h',
    'mean_positive_last_hour','mean_negative_last_hour','mean_neutral_last_hour',
    'signed_sentiment_std_24h']


def load_scores(path,news_manifest,articles):
    report=json.loads(path.read_bytes())
    if report['status']!='completed_private_finbert_sentiment_only': raise ValueError('Completed sentiment cache required')
    context=report['context']
    if context['protocol']!=PROTOCOL or context['news_manifest_sha256']!=hashlib.sha256(news_manifest.read_bytes()).hexdigest():
        raise ValueError('Sentiment protocol or source archive changed')
    if context['model_files']['pytorch_model.bin']!=WEIGHT_SHA: raise ValueError('Unpinned sentiment model')
    source=Path('finbert_headline_inference.py').read_bytes().replace(b'\r\n',b'\n')
    if context['source_sha256']!=hashlib.sha256(source).hexdigest(): raise ValueError('Sentiment inference source changed')
    scores=report['scores'];wanted={text_digest(a['headline']) for a in articles}
    if set(scores)!=wanted or report['completed_headlines']!=len(wanted): raise ValueError('Missing or extraneous sentiment scores')
    for values in scores.values(): verify_probability(values)
    return scores,report


def index_scores(articles,scores,symbols):
    result={s:[] for s in symbols};wanted=set(symbols);seen=set()
    for item in articles:
        if item['id'] in seen: raise ValueError('Duplicate article id')
        seen.add(item['id']);created=timestamp(item['created_at']);updated=timestamp(item['updated_at'])
        if updated<created: raise ValueError('Reversed article timestamps')
        values=scores[text_digest(item['headline'])];verify_probability(values)
        for symbol in sorted(wanted&set(item['symbols'])): result[symbol].append((updated,values))
    return {s:dict(records=sorted(rows,key=lambda r:r[0]),times=sorted(r[0] for r in rows)) for s,rows in result.items()}


def sentiment_features(index,symbol,date):
    cutoff=datetime.combine(datetime.fromisoformat(date).date(),time(10),ZoneInfo('America/New_York'))
    entry=index[symbol]
    def window(hours):
        a=bisect_left(entry['times'],cutoff-timedelta(hours=hours));b=bisect_left(entry['times'],cutoff)
        return [r[1] for r in entry['records'][a:b]]
    daily=window(24);recent=window(1)
    means=lambda rows:[sum(r[i] for r in rows)/len(rows) if rows else 0. for i in range(3)]
    signed=[r[0]-r[1] for r in daily];mean=sum(signed)/len(signed) if signed else 0.
    spread=math.sqrt(sum((x-mean)**2 for x in signed)/len(signed)) if signed else 0.
    return means(daily)+means(recent)+[spread]


def add_sentiment(rows,index):
    return [dict(r,features=r['features']+sentiment_features(index,r['symbol'],r['date'])) for r in rows]
