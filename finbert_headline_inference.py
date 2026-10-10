"""Pinned, offline CPU sentiment scoring. NEVER a trading profit probability.

Run in the separate NLP environment, not the production/frozen forecast venv.
No trading API, broker credentials, refitting or remote model code execution.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import time

MODEL='ProsusAI/finbert'
REVISION='4556d13015211d73dccd3fdd39d39232506f3e43'  # Public checkpoint2023, before study2024.
WEIGHT_SHA='e15a7b5738df7f17553399b6d94c6e2ff69c89245d066e8e5d183f5803a554e3'
FILES=['config.json','tokenizer_config.json','special_tokens_map.json','vocab.txt','README.md','pytorch_model.bin']
PROTOCOL=dict(model=MODEL,revision=REVISION,weight_sha256=WEIGHT_SHA,
    max_tokens=96,batch_size=32,cpu_threads=4,precision='float32',quantized=False,
    labels=['positive','negative','neutral'],trust_remote_code=False,weights_only=True,
    sentiment_is_profit_probability=False,orders=False,production_approved=False)


def digest(raw): return hashlib.sha256(raw).hexdigest()
def text_digest(text): return digest(text.encode('utf-8'))


def verify_probability(values):
    if len(values)!=3 or any(not math.isfinite(v) or not 0<=v<=1 for v in values):
        raise ValueError('Invalid sentiment probabilities')
    if not math.isclose(sum(values),1,abs_tol=1e-5): raise ValueError('Sentiment probabilities do not sum to one')


def news_texts(directory):
    raw=(directory/'manifest.json').read_bytes();manifest=json.loads(raw)
    if manifest['status']!='completed_private_historical_news_download': raise ValueError('Complete news archive required')
    texts={};ids={}
    for chunk in manifest['chunks']:
        if not chunk['complete']: raise ValueError('Incomplete news interval')
        for page in chunk['pages']:
            body=(directory/page['path']).read_bytes()
            if digest(body)!=page['sha256']: raise ValueError('News page digest mismatch')
            for article in json.loads(body)['news']:
                headline=article['headline']
                if not isinstance(headline,str) or not headline.strip(): raise ValueError('Empty or invalid headline')
                key=text_digest(headline)
                if key in texts and texts[key]!=headline: raise ValueError('Headline hash collision')
                texts[key]=headline
                identity=digest(json.dumps(article,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode())
                if article['id'] in ids and ids[article['id']]!=identity: raise ValueError('Contradictory article revision')
                ids[article['id']]=identity
    return texts,digest(raw),len(ids)


def snapshot(directory):
    import requests
    directory.mkdir(parents=True,exist_ok=True)
    response=requests.get(f'https://huggingface.co/api/models/{MODEL}/revision/{REVISION}',
        params={'blobs':'true'},timeout=30);response.raise_for_status();metadata=response.json()
    if metadata['sha']!=REVISION: raise ValueError('Unpinned model response')
    files={x['rfilename']:x for x in metadata['siblings']};hashes={}
    if files['pytorch_model.bin']['lfs']['sha256']!=WEIGHT_SHA: raise ValueError('Published weight digest changed')
    for name in FILES:
        target=directory/name
        if not target.exists():
            received=requests.get(f'https://huggingface.co/{MODEL}/resolve/{REVISION}/{name}',stream=True,timeout=60)
            received.raise_for_status()
            with target.open('xb') as handle:
                for block in received.iter_content(1024*1024): handle.write(block)
        body=target.read_bytes();entry=files[name]
        expected=entry.get('lfs',{}).get('sha256')
        if expected:
            if digest(body)!=expected: raise ValueError('Downloaded weight digest mismatch')
        else:
            git_blob=hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest()
            if git_blob!=entry['blobId']: raise ValueError('Downloaded configuration blob mismatch')
        hashes[name]=digest(body)
    record=dict(model=MODEL,revision=REVISION,files=hashes,
        retrieved_utc=datetime.now(timezone.utc).isoformat())
    (directory/'snapshot_receipt.json').write_text(json.dumps(record,indent=2))
    return hashes


def checked_batch(path,expected_keys,context):
    data=json.loads(path.read_bytes())
    if data['context']!=context or list(data['scores'])!=expected_keys:
        raise ValueError('Incompatible inference checkpoint')
    for values in data['scores'].values(): verify_probability(values)
    return data['scores']


def run(news,model_dir,output):
    import torch
    import transformers
    from transformers import AutoTokenizer,AutoModelForSequenceClassification
    if torch.__version__!='2.13.0+cpu' or transformers.__version__!='4.57.3':
        raise ValueError('Dedicated pinned CPU runtime required')
    torch.set_num_threads(4);torch.manual_seed(19);torch.use_deterministic_algorithms(True)
    texts,news_sha,article_count=news_texts(news);model_hashes=snapshot(model_dir)
    os.environ['HF_HUB_OFFLINE']='1'
    tokenizer=AutoTokenizer.from_pretrained(str(model_dir),trust_remote_code=False,local_files_only=True)
    model=AutoModelForSequenceClassification.from_pretrained(str(model_dir),
        trust_remote_code=False,local_files_only=True,use_safetensors=False,weights_only=True).eval()
    label_order=[str(model.config.id2label[i]).lower() for i in range(3)]
    if set(label_order)!=set(PROTOCOL['labels']): raise ValueError('Unexpected model class meanings')
    positions=[label_order.index(label) for label in PROTOCOL['labels']]
    packages={n:importlib.metadata.version(n) for n in ['torch','transformers','numpy','tokenizers','safetensors']}
    context=dict(protocol=PROTOCOL,news_manifest_sha256=news_sha,model_files=model_hashes,
        packages=packages,source_sha256=digest(Path(__file__).read_bytes().replace(b'\r\n',b'\n')))
    output.mkdir(parents=True,exist_ok=True);(output/'batches').mkdir(exist_ok=True)
    keys=sorted(texts);scores={};started=time.monotonic()
    report=dict(status='running_private_finbert_sentiment_only',context=context,
        unique_headlines=len(keys),articles=article_count,completed_headlines=0,
        independent_validation_pass=False,production_approved=False,orders=False)
    for first in range(0,len(keys),PROTOCOL['batch_size']):
        chosen=keys[first:first+PROTOCOL['batch_size']];target=output/'batches'/f'{first:06d}.json'
        if target.exists(): values=checked_batch(target,chosen,context)
        else:
            encoded=tokenizer([texts[k] for k in chosen],padding=True,truncation=True,
                max_length=PROTOCOL['max_tokens'],return_tensors='pt')
            with torch.inference_mode(): probabilities=torch.softmax(model(**encoded).logits,dim=-1).cpu().tolist()
            values={k:[float(p[i]) for i in positions] for k,p in zip(chosen,probabilities)}
            for p in values.values(): verify_probability(p)
            with target.open('x') as handle: json.dump(dict(context=context,scores=values),handle,allow_nan=False)
        scores.update(values);report['completed_headlines']=len(scores)
        if first%1600==0 or len(scores)==len(keys):
            (output/'status.json').write_text(json.dumps(report,indent=2,allow_nan=False))
            print(json.dumps(dict(completed_headlines=len(scores),total_headlines=len(keys),
                elapsed_seconds=round(time.monotonic()-started,1),orders=False)),flush=True)
    report.update(status='completed_private_finbert_sentiment_only',scores=scores,
        limitations=['Sentiment classes are not future return probabilities',
            'Published checkpoint predates2024 outcomes, but this is not original headline delivery proof',
            '96-token truncation, headline-only context and stock attribution may distort sentiment',
            'No forecasting/trading profit validation performed by this inference cache'])
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    report.pop('scores');(output/'status.json').write_text(json.dumps(report,indent=2,allow_nan=False));return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--news',type=Path,default=Path('cache/news_context'))
    p.add_argument('--model',type=Path,default=Path('cache/finbert_model'))
    p.add_argument('--output',type=Path,default=Path('cache/finbert_scores'))
    a=p.parse_args();run(a.news,a.model,a.output)
