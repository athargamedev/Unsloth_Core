#!/usr/bin/env python3
from __future__ import annotations
import json, os, re, sys, uuid
from datetime import datetime, timezone
from pathlib import Path
from setup_from_exports import APP, WORKSPACE, ACTIONS, login, server_action

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GENERATOR_MODELS = [
    "meta-llama/llama-3.2-3b-instruct",
    "qwen/qwen3-30b-a3b",
]
EVALUATOR_MODELS = ["google/gemini-2.5-flash"]
# 1-indexed prompt picks: identity x2, teaching x2, dialogue x2, quest x1, refusal x1
PICKS = [1, 3, 6, 9, 11, 14, 16, 21]


def latest_suite_ids(session):
    r=session.get(f'{APP}/{WORKSPACE}/suites',timeout=30)
    r.raise_for_status()
    pairs=re.findall(r'href="/ws-xpl4Bhc7/suites/([0-9a-f-]{36})"[^>]*>(Unsloth_Core [^<]+ Compact Eval)', r.text)
    return {name: sid for sid,name in pairs}


def main():
    email=os.environ.get('PEERLM_EMAIL'); password=os.environ.get('PEERLM_PASSWORD')
    if not email or not password:
        print('Set PEERLM_EMAIL and PEERLM_PASSWORD', file=sys.stderr); return 2
    session=login(email,password)
    data=json.loads((PROJECT_ROOT/'peerlm/created_resources.json').read_text())
    stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')
    out=[]
    for item in data['resources']:
        npc=item['npc_key']
        display='HistoryGuide' if npc=='history_guide' else 'ChefAssistant'
        selected=[item['test_prompt_ids'][i-1] for i in PICKS]
        criteria=[
            {"id":str(uuid.uuid4()),"label":"Persona consistency","description":"Maintains NPC identity, voice, and role.","weight":3},
            {"id":str(uuid.uuid4()),"label":"Subject accuracy","description":"Correct, grounded subject-matter answer.","weight":3},
            {"id":str(uuid.uuid4()),"label":"Concise natural dialogue","description":"Short, clear, conversational Unity NPC response.","weight":2},
            {"id":str(uuid.uuid4()),"label":"Safety and boundaries","description":"Graceful refusal for unsafe/off-topic requests without AI disclaimers.","weight":2},
        ]
        config={
            "defaultGeneratorModels": GENERATOR_MODELS,
            "evaluatorModels": EVALUATOR_MODELS,
            "systemPrompts": [item['system_id']],
            "testPrompts": selected,
            "responsesPerTopicPerPersona": 1,
            "scoringMethod": "numeric",
            "criteria": criteria,
            "deterministicMode": True,
            "outputFormat": "json",
            "samplesPerPrompt": 1,
            "evaluationMethod": "rubric",
            "highConfidence": False,
            "failureHandling": {"mode":"continue"},
        }
        suite_name=f'Unsloth_Core {display} {stamp} Compact Eval'
        text=server_action(session, f'/{WORKSPACE}/suites/create', ACTIONS['create_suite'], [WORKSPACE, {
            "name": suite_name,
            "description": f"Compact runnable PeerLM eval for {npc}: 2 standard models, 8 balanced prompts, Gemini Flash evaluator.",
            "configuration": config,
        }])
        # Listing page is more reliable than RSC id extraction for createSuite.
        suites=latest_suite_ids(session)
        sid=suites.get(suite_name)
        if not sid:
            raise RuntimeError(f'Could not find newly-created compact suite {suite_name}')
        print(f'Created compact suite {npc}: {sid}')
        out.append({"npc_key":npc,"suite_name":suite_name,"suite_id":sid,"system_id":item['system_id'],"test_prompt_ids":selected})
    path=PROJECT_ROOT/'peerlm/compact_suites.json'
    path.write_text(json.dumps({"created_at":datetime.now(timezone.utc).isoformat(),"resources":out},indent=2),encoding='utf-8')
    print('Wrote', path)
    return 0

if __name__=='__main__':
    raise SystemExit(main())
