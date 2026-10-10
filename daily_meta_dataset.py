"""Join owned SIP/raw research caches with immutable provenance, no broker API."""
import argparse
import json
from pathlib import Path

import pandas as pd

from active_stock_research import SYMBOLS,hash_file
from prospective_outcome_audit import save_once_or_identical


def combine_frames(frames,symbol):
    if not frames: raise ValueError('At least one source required')
    columns=set(frames[0].columns)
    if not {'symbol','timestamp','open','high','low','close','volume'}<=columns:
        raise ValueError('Missing source market columns')
    for frame in frames:
        if set(frame.columns)!=columns or set(frame.symbol)!={symbol}:
            raise ValueError('Source schema/symbol mismatch')
    joined=pd.concat(frames,ignore_index=True)
    joined['timestamp']=pd.to_datetime(joined['timestamp'],utc=True)
    joined=joined.drop_duplicates()
    if joined.duplicated(['symbol','timestamp']).any():
        raise ValueError('Conflicting overlapping market observations; do not choose revisions silently')
    return joined.sort_values(['timestamp','symbol']).reset_index(drop=True)


def join(sources,output):
    output.mkdir(parents=True,exist_ok=True)
    for symbol in SYMBOLS:
        frames=[];provenance=[]
        for directory in sources:
            path=directory/f'{symbol}.csv'
            metadata=json.loads(path.with_suffix('.metadata.json').read_text())
            actual=hash_file(path)
            if metadata.get('feed')!='sip' or metadata.get('adjustment')!='raw' or metadata.get('sha256')!=actual:
                raise ValueError('SIP/raw source byte hash mismatch')
            provenance.append(dict(path=str(path),sha256=actual,metadata=metadata))
            frames.append(pd.read_csv(path))
        joined=combine_frames(frames,symbol)
        path=output/f'{symbol}.csv'
        save_once_or_identical(path,joined.to_csv(index=False).encode())
        metadata=dict(symbol=symbol,feed='sip',adjustment='raw',sha256=hash_file(path),rows=len(joined),
            status='exploratory_owned_cache_join',input_sources=provenance,
            first_timestamp=str(joined.timestamp.iloc[0]),last_timestamp=str(joined.timestamp.iloc[-1]))
        save_once_or_identical(path.with_suffix('.metadata.json'),json.dumps(metadata,indent=2).encode())
        print(json.dumps(dict(symbol=symbol,rows=len(joined),sources=len(sources),source_files_unchanged=True)),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,action='append',required=True)
    parser.add_argument('--output',type=Path,default=Path('cache/daily_meta_extended'))
    args=parser.parse_args();join(args.source,args.output)
