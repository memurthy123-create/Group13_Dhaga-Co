"""python -m scripts.evaluate [--live]; held-out synthetic labels, not real client evidence."""
import argparse
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv
from dhaga.models import ModelGateway
from dhaga.workflows import read_input, process

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')

def run(live=False):
    gateway = ModelGateway(live=live)
    results = {}
    for task, file, label_file, key in [('returns','returns.csv','return_labels.csv','message_id'), ('catalogue','catalogue.csv','catalogue_labels.csv','sku')]:
        labels=pd.read_csv(ROOT/'data'/label_file, keep_default_na=False)
        selected=set(labels[key])
        raw=[r for r in read_input(ROOT/'data'/file, task) if r[key] in selected]
        outputs=process(raw, task, gateway, catalogue_skus=set(pd.read_csv(ROOT/'data/catalogue.csv').sku))
        by_id={r['record_id']:r for r in outputs}
        scores=[]
        for _, label in labels.iterrows():
            r=by_id[label[key]]
            fields=['primary_reason'] if task=='returns' else ['colour_family','fabric','size_label']
            correct=bool(r['decision']) and all(r['decision'][field]==label['expected_'+field] for field in fields)
            scores.append({'id':label[key],'correct':correct,'status':r['status']})
        frame=pd.DataFrame(scores)
        results[task]={'records':len(frame),'exact_match':round(frame.correct.mean(),3),'review_or_failure':int(frame.status.isin(['needs_review','failed']).sum())}
        print(task, results[task])
    print('Synthetic exact-match results only. Offline mode is not evidence of live model quality.')
    return results

if __name__=='__main__':
    args=argparse.ArgumentParser(); args.add_argument('--live',action='store_true')
    run(args.parse_args().live)
