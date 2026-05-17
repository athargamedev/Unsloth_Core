#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path
from setup_from_exports import APP, WORKSPACE, login, server_action

ACTIONS = {
    'estimate_run_cost': '703b2b744ae1795e3e4b0bd406b1468716a62d142c',
    'trigger_run': '78f0222a489a632088994612cb694ef435517e5a30',
}
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def extract_json_tail(text: str):
    # Next server actions often include the returned JSON object as a line like 1:{...}
    candidates = []
    for line in text.splitlines():
        if ':' in line:
            _, rest = line.split(':', 1)
            rest = rest.strip()
            if rest.startswith('{') or rest.startswith('['):
                try:
                    candidates.append(json.loads(rest))
                except Exception:
                    pass
    return candidates[-1] if candidates else {'raw': text[:1000]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--email', default=os.environ.get('PEERLM_EMAIL'))
    ap.add_argument('--password', default=os.environ.get('PEERLM_PASSWORD'))
    ap.add_argument('--resources', default='peerlm/created_resources.json')
    ap.add_argument('--run', action='store_true', help='Actually trigger runs after estimating cost')
    args = ap.parse_args()
    if not args.email or not args.password:
        print('Set PEERLM_EMAIL and PEERLM_PASSWORD', file=sys.stderr); return 2
    session = login(args.email, args.password)
    resources = json.loads((PROJECT_ROOT / args.resources).read_text())['resources']
    outputs=[]
    total_credits=0
    for item in resources:
        suite_id=item['suite_id']; npc=item['npc_key']
        path=f'/{WORKSPACE}/suites/{suite_id}'
        estimate_text=server_action(session,path,ACTIONS['estimate_run_cost'],[WORKSPACE,suite_id])
        estimate=extract_json_tail(estimate_text)
        print(f'Estimate {npc}:', json.dumps(estimate, indent=2)[:1000])
        credits = estimate.get('total') or estimate.get('credits') or estimate.get('breakdown',{}).get('total') or 0
        try: total_credits += int(credits)
        except Exception: pass
        record={'npc_key':npc,'suite_id':suite_id,'estimate':estimate}
        if args.run:
            run_text=server_action(session,path,ACTIONS['trigger_run'],[WORKSPACE,suite_id])
            run_result=extract_json_tail(run_text)
            print(f'Run {npc}:', json.dumps(run_result, indent=2)[:1000])
            record['run_result']=run_result
        outputs.append(record)
    print('Estimated total credits:', total_credits)
    out=PROJECT_ROOT/'peerlm/run_requests.json'
    out.write_text(json.dumps(outputs, indent=2), encoding='utf-8')
    print('Wrote', out)
    return 0

if __name__=='__main__':
    raise SystemExit(main())
