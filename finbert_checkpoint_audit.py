"""Reproduce fixed sentiment batches. Spot checks are not economic validation."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
from finbert_headline_inference import PROTOCOL,WEIGHT_SHA,news_texts,checked_batch,verify_probability

FIXED_BATCH_STARTS=[0,8000,16000,32000,56000]


def compare(expected,actual,tolerance=1e-7):
    if set(expected)!=set(actual): raise ValueError('Reproduction headline membership changed')
    maximum=0.
    for key in expected:
        verify_probability(expected[key]);verify_probability(actual[key])
        maximum=max(maximum,max(abs(a-b) for a,b in zip(expected[key],actual[key])))
    if maximum>tolerance: raise ValueError('Sentiment outputs not reproduced within fixed tolerance')
    return maximum


def audit(news,model_dir,cache,output,partial=False):
    import torch,transformers
    from transformers import AutoTokenizer,AutoModelForSequenceClassification
    status=json.loads((cache/'status.json').read_bytes());context=status['context']
    if not partial and status['status']!='completed_private_finbert_sentiment_only':
        raise ValueError('Full fixed-batch audit requires completed inference')
    if context['protocol']!=PROTOCOL: raise ValueError('Inference protocol changed')
    source=Path('finbert_headline_inference.py').read_bytes().replace(b'\r\n',b'\n')
    if hashlib.sha256(source).hexdigest()!=context['source_sha256']: raise ValueError('Inference source changed')
    for name,expected in context['packages'].items():
        if importlib.metadata.version(name)!=expected: raise ValueError('Inference runtime changed')
    for name,expected in context['model_files'].items():
        if hashlib.sha256((model_dir/name).read_bytes()).hexdigest()!=expected: raise ValueError('Model file changed')
    if context['model_files']['pytorch_model.bin']!=WEIGHT_SHA: raise ValueError('Unpinned model')
    texts,news_sha,count=news_texts(news)
    if context['news_manifest_sha256']!=news_sha: raise ValueError('News archive changed')
    torch.set_num_threads(PROTOCOL['cpu_threads']);torch.manual_seed(19);torch.use_deterministic_algorithms(True)
    tokenizer=AutoTokenizer.from_pretrained(str(model_dir),trust_remote_code=False,local_files_only=True)
    model=AutoModelForSequenceClassification.from_pretrained(str(model_dir),trust_remote_code=False,
        local_files_only=True,use_safetensors=False,weights_only=True).eval()
    labels=[str(model.config.id2label[i]).lower() for i in range(3)]
    positions=[labels.index(label) for label in PROTOCOL['labels']]
    keys=sorted(texts);checks=[];missing=[]
    for first in FIXED_BATCH_STARTS:
        selected=keys[first:first+PROTOCOL['batch_size']];target=cache/'batches'/f'{first:06d}.json'
        if not target.exists():
            if not partial: raise ValueError('Required fixed batch missing')
            missing.append(first);continue
        expected=checked_batch(target,selected,context)
        encoded=tokenizer([texts[k] for k in selected],padding=True,truncation=True,
            max_length=PROTOCOL['max_tokens'],return_tensors='pt')
        with torch.inference_mode(): probabilities=torch.softmax(model(**encoded).logits,dim=-1).cpu().tolist()
        actual={k:[float(p[i]) for i in positions] for k,p in zip(selected,probabilities)}
        checks.append(dict(first=first,headlines=len(selected),maximum_absolute_difference=compare(expected,actual),
            checkpoint_sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
    report=dict(status='partial_fixed_batch_reproduction' if partial else 'completed_fixed_batch_reproduction',
        checks=checks,missing_fixed_batches=missing,all_fixed_batches_checked=not missing,
        entire_corpus_outputs_reproduced=False,economic_validation=False,
        independent_validation_pass=False,production_approved=False,orders=False,
        limitations=['Fixed spot checks do not independently reproduce every headline score',
            'Original news delivery and lost text versions remain unauthenticated',
            'Sentiment reproduction is not future stock prediction or profitable trading evidence'])
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps(report));return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--partial',action='store_true')
    p.add_argument('--news',type=Path,default=Path('cache/news_context'))
    p.add_argument('--model',type=Path,default=Path('cache/finbert_model'))
    p.add_argument('--cache',type=Path,default=Path('cache/finbert_scores'))
    p.add_argument('--output',type=Path,default=Path('research_runs/finbert_checkpoint_audit/results.json'))
    a=p.parse_args();audit(a.news,a.model,a.cache,a.output,a.partial)
