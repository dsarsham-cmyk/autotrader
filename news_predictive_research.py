"""Matched headline-event ablation on exposed dates. No orders or NLP oracle."""
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
from news_event_features import index_news,add_news,FEATURES


def run(data,news,reference,output):
    original=json.loads(reference.read_text())
    if original['status']!='completed_exposed_causal_sparse_research': raise ValueError('Completed causal reference required')
    for n,h in original['dependency_sha256'].items():
        if hashlib.sha256(Path(n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=h:
            raise ValueError('Reference source changed')
    articles,news_manifest=load_news(news)
    observations,evidence=load_observations(data)
    if evidence!=original['evidence']: raise ValueError('Reference market inputs changed')
    by_date,reasons=opening_rows(observations)
    rows=[r for date,stocks in sorted(by_date.items()) for symbol,r in sorted(stocks.items())]
    enriched=add_news(rows,index_news(articles,SYMBOLS));market=market_maps(observations)
    output.mkdir(parents=True,exist_ok=True)
    report=dict(status='running_exposed_historical_news_ablation',
        protocol=dict(feature_sets=['causal_price','causal_price_plus_headline_events'],
            models=['logistic','boosted'],thresholds=[.5,.65,.9],news_features=FEATURES,
            news_window_hours=24,news_latest_version_cutoff='strictly before10:00NY',
            original_text_versions_recovered=False,trading_limits_unchanged=True),
        evidence=evidence,news_manifest_sha256=hashlib.sha256((news/'manifest.json').read_bytes()).hexdigest(),
        reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),
        news_unique_articles=len(articles),opening_rows=len(rows),
        opening_rows_with_news=sum(r['features'][-len(FEATURES)]>0 for r in enriched),
        dependency_sha256=dict(original['dependency_sha256'],**{n:hashlib.sha256(Path(n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for n in ['news_predictive_research.py','news_event_features.py','news_research_cache.py']}),
        cases=[],orders=False,production_approved=False,independent_validation_pass=False,
        limitations=['All stock outcomes already exposed; new historical input is not independent forward validation',
            'Latest retained text is assigned at provider revision time, not backdated to original publication',
            'Original versions absent from this archive are not recovered; historical version omission can bias features',
            'Provider timestamps do not authenticate original delivery or availability before an actual trade',
            'Headline token/event rules are fixed crude proxies, not trained FinBERT, verified sentiment or causality',
            'No-news zeros mean no retained version in this archive/window, not proof no actual news existed',
            'Current fixed universe, raw corporate actions, missing calendar days and OHLC assumptions remain'])
    with threadpool_limits(limits=1):
        for name,inputs in [('causal_price',rows),('causal_price_plus_headline_events',enriched)]:
            for kind in ['logistic','boosted']:
                forecasts,folds=walk(inputs,market,kind)
                case=dict(feature_set=name,model=kind,folds=folds,outcomes=[])
                for threshold in [.5,.65,.9]:
                    for cost,delay in [(10,16),(20,16),(10,17)]:
                        result=portfolio(forecasts,market,threshold,cost,delay)
                        result['known_prefix_metrics']=accounting_metrics(result,forecasts)
                        result['known_prefix_cost_diagnostic']=diagnostic(dict(result,profit_usd=result['known_prefix_profit_usd']))
                        if name=='causal_price':
                            old=next(c for c in original['cases'] if c['model']==kind)
                            expected=next(o for o in old['outcomes'] if (o['threshold'],o['costs_bps'],o['delay'])==(threshold,cost,delay))
                            if any(result[k]!=expected[k] for k in ['profit_usd','daily','trades','unknown_selections']):
                                raise ValueError('Price reference not reproduced')
                        case['outcomes'].append(result)
                        if cost==10 and delay==16:
                            print(json.dumps(dict(features=name,model=kind,gate=threshold,
                                active_days=result['active_days'],win_rate=result['active_day_win_rate_pct'],
                                net_usd=result['profit_usd'],complete=result['full_period_coverage_complete'])),flush=True)
                report['cases'].append(case)
                (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    report['status']='completed_exposed_historical_news_ablation'
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False));return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    p.add_argument('--news',type=Path,default=Path('cache/news_context'))
    p.add_argument('--reference',type=Path,default=Path('research_runs/causal_sparse/results.json'))
    p.add_argument('--output',type=Path,default=Path('research_runs/news_ablation'))
    a=p.parse_args();run(a.data,a.news,a.reference,a.output)
