"""Matched headline-event versus pretrained FinBERT sentiment inputs. NO ORDERS."""
import argparse
import hashlib
import json
from pathlib import Path
from threadpoolctl import threadpool_limits
from active_stock_research import SYMBOLS
from causal_opening_inventory import load_observations,opening_rows
from causal_sparse_research import walk,market_maps
from causal_sparse_simulator import portfolio
from prospective_series_audit import accounting_metrics
from fixed_trade_cost_diagnostic import diagnostic
from news_research_cache import load_news
from news_event_features import index_news,add_news
from finbert_news_features import load_scores,index_scores,add_sentiment,FEATURES


def prefix_accounting(result,forecasts):
    """Account only observed prefix; never replace unknown full-period net."""
    return accounting_metrics(dict(result,profit_usd=result['known_prefix_profit_usd']),forecasts)


def run(data,news,sentiment,reference,output):
    original=json.loads(reference.read_bytes())
    if original['status']!='completed_exposed_historical_news_ablation': raise ValueError('Completed headline reference required')
    for n,h in original['dependency_sha256'].items():
        if hashlib.sha256(Path(n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=h: raise ValueError('Reference source changed')
    articles,news_manifest=load_news(news)
    if hashlib.sha256((news/'manifest.json').read_bytes()).hexdigest()!=original['news_manifest_sha256']:
        raise ValueError('Reference news source changed')
    scores,cache=load_scores(sentiment,news/'manifest.json',articles)
    observations,evidence=load_observations(data)
    if evidence!=original['evidence']: raise ValueError('Reference market source changed')
    by_date,reasons=opening_rows(observations)
    rows=[r for date,stocks in sorted(by_date.items()) for symbol,r in sorted(stocks.items())]
    baseline=add_news(rows,index_news(articles,SYMBOLS))
    enriched=add_sentiment(baseline,index_scores(articles,scores,SYMBOLS));market=market_maps(observations)
    output.mkdir(parents=True,exist_ok=True)
    report=dict(status='running_exposed_finbert_input_ablation',evidence=evidence,
        protocol=dict(feature_sets=['headline_events','headline_events_plus_finbert'],models=['logistic','boosted'],
            sentiment_features=FEATURES,sentiment_is_profit_probability=False,trading_limits_unchanged=True),
        sentiment_context=cache['context'],sentiment_cache_sha256=hashlib.sha256(sentiment.read_bytes()).hexdigest(),
        reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),
        dependency_sha256=dict(original['dependency_sha256'],**{n:hashlib.sha256(Path(n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for n in ['finbert_headline_inference.py','finbert_news_features.py','finbert_predictive_research.py']}),
        cases=[],orders=False,production_approved=False,independent_validation_pass=False,
        limitations=['Exposed market outcomes and latest news versions: not independent validation',
            'Pretrained sentiment checkpoint predates study but sentiment is not future stock direction',
            'FinBERT is frozen; only downstream classifiers fit/calibrate on past outcomes',
            '96-token headline truncation and multiple stock attribution can distort sentiment',
            'Latest text never backdated before revision; lost original versions and original receipt remain unverified',
            'Fixed universe, raw corporate actions, calendar gaps and OHLC/guard assumptions remain'])
    with threadpool_limits(limits=1):
        for name,inputs in [('headline_events',baseline),('headline_events_plus_finbert',enriched)]:
            for kind in ['logistic','boosted']:
                forecasts,folds=walk(inputs,market,kind);case=dict(feature_set=name,model=kind,folds=folds,outcomes=[])
                for threshold in [.5,.65,.9]:
                    for cost,delay in [(10,16),(20,16),(10,17)]:
                        result=portfolio(forecasts,market,threshold,cost,delay)
                        result['known_prefix_metrics']=prefix_accounting(result,forecasts)
                        result['known_prefix_cost_diagnostic']=diagnostic(dict(result,profit_usd=result['known_prefix_profit_usd']))
                        if name=='headline_events':
                            old=next(c for c in original['cases'] if c['feature_set']=='causal_price_plus_headline_events' and c['model']==kind)
                            expected=next(o for o in old['outcomes'] if (o['threshold'],o['costs_bps'],o['delay'])==(threshold,cost,delay))
                            if any(result[k]!=expected[k] for k in ['profit_usd','daily','trades','unknown_selections']):
                                raise ValueError('Headline baseline not reproduced')
                        case['outcomes'].append(result)
                        if cost==10 and delay==16:
                            print(json.dumps(dict(features=name,model=kind,gate=threshold,active_days=result['active_days'],
                                win_rate=result['active_day_win_rate_pct'],net_usd=result['profit_usd'],
                                complete=result['full_period_coverage_complete'])),flush=True)
                report['cases'].append(case);(output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    report['status']='completed_exposed_finbert_input_ablation'
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False));return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    p.add_argument('--news',type=Path,default=Path('cache/news_context'))
    p.add_argument('--sentiment',type=Path,default=Path('cache/finbert_scores/results.json'))
    p.add_argument('--reference',type=Path,default=Path('research_runs/news_ablation/results.json'))
    p.add_argument('--output',type=Path,default=Path('research_runs/finbert_ablation'))
    a=p.parse_args();run(a.data,a.news,a.sentiment,a.reference,a.output)
