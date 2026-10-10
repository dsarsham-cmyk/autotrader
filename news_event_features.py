"""Fixed headline event features, not a trained language model or oracle."""
from bisect import bisect_left
from datetime import datetime,time,timedelta
import math
import re
from zoneinfo import ZoneInfo
from prospective_forecast_evidence import timestamp

FEATURES=['log_news_versions_24h','log_news_versions_last_hour',
    'earnings_fraction','guidance_fraction','deal_fraction','payout_fraction',
    'regulatory_fraction','analyst_fraction','positive_token_fraction',
    'negative_token_fraction','multi_symbol_fraction']
GROUPS=[{'earnings','eps','results','quarterly','profit','revenue'},
    {'guidance','outlook','forecast','forecasts'},
    {'acquisition','acquire','acquires','merger','deal','partnership'},
    {'dividend','dividends','buyback','repurchase'},
    {'lawsuit','probe','investigation','antitrust','regulator','regulatory','ban'},
    {'analyst','analysts','upgrade','downgrade','target','rating'},
    {'beats','beat','raises','raised','upgrade','upgraded','growth','record','surges'},
    {'misses','miss','cuts','cut','downgrade','downgraded','loss','losses','falls','declines'}]


def index_news(articles,symbols):
    wanted=set(symbols);indexed={s:[] for s in symbols};seen=set()
    for item in articles:
        if item['id'] in seen: raise ValueError('Duplicate article id')
        seen.add(item['id']);created=timestamp(item['created_at']);updated=timestamp(item['updated_at'])
        if updated<created: raise ValueError('Article revision before creation')
        linked=item['symbols']
        if not isinstance(linked,list) or any(not isinstance(s,str) for s in linked):
            raise ValueError('Invalid article symbols')
        headline=item['headline']
        if not isinstance(headline,str): raise ValueError('Invalid article headline')
        tokens=set(re.findall(r'[a-z]+',headline.lower()))
        # Treat this retained VERSION as appearing at its update time. Never
        # backdate its latest text to original publication before a revision.
        record=(updated,tuple(bool(tokens&g) for g in GROUPS),len(set(linked))>1)
        for symbol in sorted(wanted&set(linked)): indexed[symbol].append(record)
    return {s:dict(records=sorted(rows,key=lambda x:x[0]),times=sorted(r[0] for r in rows))
        for s,rows in indexed.items()}


def features(index,symbol,date):
    cutoff=datetime.combine(datetime.fromisoformat(date).date(),time(10),ZoneInfo('America/New_York'))
    entries=index[symbol];left=cutoff-timedelta(hours=24)
    lo=bisect_left(entries['times'],left);hi=bisect_left(entries['times'],cutoff)
    selected=entries['records'][lo:hi];count=len(selected)
    recent=sum(r[0]>=cutoff-timedelta(hours=1) for r in selected)
    fractions=[sum(r[1][i] for r in selected)/count if count else 0. for i in range(len(GROUPS))]
    multi=sum(r[2] for r in selected)/count if count else 0.
    return [math.log1p(count),math.log1p(recent)]+fractions+[multi]


def add_news(rows,index):
    return [dict(row,features=row['features']+features(index,row['symbol'],row['date'])) for row in rows]
