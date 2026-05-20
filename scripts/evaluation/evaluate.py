#!/usr/bin/env python3
"""
evaluate.py — Side-by-Side Model Evaluator

This script performs deep comparisons between two GGUF models. It uses
heuristics and an optional LLM judge to score responses based on persona,
accuracy, and conversational constraints.

Usage:
    ./ucore evaluate --baseline old.gguf --candidate new.gguf --spec subjects/NPC_specs/npc.json
    python scripts/evaluation/evaluate.py --model model.gguf --val-data validation.jsonl

Technical Details:
- Input: One or two GGUF models, subject spec, and validation dataset.
- Output: Markdown and HTML reports with metrics, charts, and winner analysis.
- Features: Lexical diversity scoring, constraint checking, and interactive chat.
"""

import argparse
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
import requests
import urllib.request
import urllib.error
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from _config import paths
from _config.log_setup import log_info, log_warn, log_error, log_state

# ── Constraint checking ─────────────────────────────────────────────────────

def check_sentence_count(text, max_sentences=3):
    """Check if response obeys the max sentence rule."""
    sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
    return len(sentences) <= max_sentences, len(sentences)


def check_contains_name(text, name=None):
    """Check if response contains the persona name."""
    if not name:
        return True, 0
    count = text.lower().count(name.lower())
    return count > 0, count


def identity_prompt_requires_name(question: str) -> bool:
    """Return True when the user is explicitly asking for NPC identity/name.

    Normal teaching/dialogue turns should not be forced to repeat the persona
    name. The name check is only meaningful for self-introduction prompts.
    """
    q = (question or "").strip().lower()
    identity_patterns = [
        r"\bwho are you\b",
        r"\bwhat is your name\b",
        r"\bwhat's your name\b",
        r"\btell me about yourself\b",
        r"\bintroduce yourself\b",
        r"\bwho do you teach\b",
        r"\bwhat can you tell me about\b",
    ]
    return any(re.search(pattern, q) for pattern in identity_patterns)


GENERIC_FILLER_PATTERNS = [
    "once you understand",
    "everything falls into place",
    "let me tell you something about it",
    "what i think is really important",
    "the key to understanding",
    "not that hard once you understand",
    "that's the key piece",
    "that's what really matters",
]


def _flatten_spec_terms(spec=None):
    """Extract rough domain terms from an NPC spec for heuristic scoring."""
    if not spec:
        return set()
    chunks = []
    for key in ("subject", "system_prompt"):
        value = spec.get(key)
        if isinstance(value, str):
            chunks.append(value)
    for concept in spec.get("concepts", []) if isinstance(spec.get("concepts"), list) else []:
        if isinstance(concept, dict):
            chunks.append(str(concept.get("name", "")))
            chunks.extend(str(alias) for alias in concept.get("aliases", []) if alias)
        elif concept:
            chunks.append(str(concept))
    text = "\n".join(chunks).lower()
    terms = set()
    for token in re.findall(r"[a-z][a-z0-9'-]{3,}", text):
        terms.add(token)
    for phrase in re.findall(r"[a-z][a-z0-9'-]+(?:\s+[a-z][a-z0-9'-]+){1,3}", text):
        if len(phrase) >= 8:
            terms.add(phrase)
    return terms


def response_specificity_score(text: str, spec=None, expected: str | None = None) -> int:
    """Estimate whether a response contains concrete, domain-specific content.

    This is intentionally lightweight: it is only used as a fallback when the
    LLM judge is absent or returns a tie. It rewards overlap with domain terms
    and expected-answer terms, and penalizes generic tutoring filler.
    """
    normalized = (text or "").lower()
    if not normalized.strip():
        return -100

    score = 0
    terms = _flatten_spec_terms(spec)
    if terms:
        matches = sum(1 for term in terms if term in normalized)
        score += min(matches, 6) * 2

    if expected:
        expected_terms = {
            t for t in re.findall(r"[a-z][a-z0-9'-]{4,}", expected.lower())
            if t not in {"about", "there", "their", "would", "could", "should"}
        }
        overlap = sum(1 for term in expected_terms if term in normalized)
        score += min(overlap, 6)

    if re.search(r"\b\d+(?:\.\d+)?\b", normalized):
        score += 1
    if any(marker in normalized for marker in ["because", "for example", "means", "causes", "allows", "helps"]):
        score += 1
    for filler in GENERIC_FILLER_PATTERNS:
        if filler in normalized:
            score -= 4
    if len(normalized.split()) < 10:
        score -= 2
    return score


def check_no_ai_disclaimer(text):
    """Check if the model claims to be an AI."""
    patterns = [
        r"\bI am (an|the) AI\b",
        r"\bAI (language model|assistant)\b",
        r"\bI('m| am) not a (real|human)\b",
        r"\bas an AI\b",
    ]
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return False, pattern
    return True, None


def check_no_think_tags(text):
    """Check if the response has think tags (should not have them)."""
    return "<｜end▁of▁thinking｜>" not in text


def diversity_score(text):
    """Compute lexical diversity metrics."""
    tokens = text.split()
    if len(tokens) < 2:
        return {"ttr": 0, "repetition": 0, "length": 0}
    unique = len(set(tokens))
    ttr = unique / len(tokens)
    bigrams = [f"{tokens[i]}_{tokens[i+1]}" for i in range(len(tokens) - 1)]
    repeats = sum(1 for v in Counter(bigrams).values() if v > 1)
    rep_rate = repeats / len(bigrams) if bigrams else 0
    return {"ttr": round(ttr, 4), "repetition": round(rep_rate, 4), "length": len(tokens)}


def quality_estimate(text):
    """Rough quality score based on token statistics (lower = better)."""
    tokens = text.split()
    if len(tokens) < 3:
        return 999
    unigrams = Counter(tokens)
    total = len(tokens)
    prob = sum(c / total for c in unigrams.values()) / len(unigrams)
    if prob <= 0:
        return 999
    return round(-math.log(prob) * 10, 2)


# ── llama.cpp server management ─────────────────────────────────────────────

class LlamaServer:
    """Manage a llama.cpp server subprocess for model inference."""

    def __init__(self, gguf_path, port=8888, host="127.0.0.1", lora_path=None, lora_weight=1.0, gpu_layers=99, max_tokens=256):
        self.gguf_path = Path(gguf_path)
        self.lora_path = Path(lora_path) if lora_path else None
        self.lora_weight = lora_weight
        self.gpu_layers = gpu_layers
        self.max_tokens = max_tokens
        self.port = port
        self.host = host
        self.process = None
        self.api_url = f"http://{host}:{port}/v1/chat/completions"

    def start(self, timeout=60):
        """Start the llama.cpp server and wait until it's ready."""
        # Try to find llama-server binary
        candidates = [
            self.gguf_path.parent / "llama-server",
            self.gguf_path.parent.parent / "llama-server",
            Path("/home/athar/.unsloth/llama.cpp/build/bin/llama-server"),
            Path.home() / ".unsloth/llama.cpp/build/bin/llama-server",
        ]
        llama_server = None
        for c in candidates:
            if c.exists():
                llama_server = c
                break

        if not llama_server:
            # Try PATH
            import shutil
            llama_server = shutil.which("llama-server")
            if not llama_server:
                # Fall back: try to find it
                search = subprocess.run(
                    ["find", "/home/athar", "-name", "llama-server", "-type", "f"],
                    capture_output=True, text=True, timeout=10
                )
                if search.stdout.strip():
                    llama_server = search.stdout.strip().split("\n")[0]

        if not llama_server:
            print("Warning: llama-server not found. Install it or provide the path.")
            print("Using direct inference via llama.cpp would require the library.")
            return False

        cmd = [
            str(llama_server),
            "-m", str(self.gguf_path),
            "--host", self.host,
            "--port", str(self.port),
            "-ngl", str(self.gpu_layers),  # GPU layers to offload (0 = CPU-only)
            "-c", "4096",   # Context size
        ]

        if self.lora_path:
            cmd.extend(["--lora", str(self.lora_path)])
            print(f"[server] LoRA adapter: {self.lora_path}")

        print(f"[server] Starting: {' '.join(cmd)}")
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Wait for server to be ready — probe HTTP endpoint, not just TCP
        import socket
        import urllib.request
        start = time.time()
        health_url = f"http://{self.host}:{self.port}/v1/models"
        while time.time() - start < timeout:
            try:
                with socket.create_connection((self.host, self.port), timeout=2):
                    # TCP is open — now wait for HTTP handler
                    pass
            except (ConnectionRefusedError, OSError):
                time.sleep(1)
                continue
            # Probe the HTTP endpoint until it responds
            probe_start = time.time()
            while time.time() - probe_start < 30:
                try:
                    with urllib.request.urlopen(
                        urllib.request.Request(health_url), timeout=5
                    ) as resp:
                        if resp.status == 200:
                            print(f"[server] Ready on {self.host}:{self.port}")
                            return True
                except (urllib.error.HTTPError, urllib.error.URLError, OSError):
                    pass
                time.sleep(2)
            break  # Probe timeout — give up

        print(f"[server] Timeout waiting for server on {self.host}:{self.port}")
        self.stop()
        return False

    def query(self, messages, max_tokens=None, temperature=0.7):
        """Send a chat completion request to the running server."""
        if max_tokens is None:
            max_tokens = self.max_tokens
        payload = json.dumps({
            "model": "default",
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }).encode()

        req = urllib.request.Request(
            self.api_url,
            data=payload,
            headers={
                "Content-Type": "application/json",
            },
        )
        try:
            start = time.time()
            with urllib.request.urlopen(req, timeout=120) as resp:
                latency = time.time() - start
                result = json.loads(resp.read())
                content = result["choices"][0]["message"]["content"]
                return content, latency
        except Exception as e:
            return f"[ERROR] {e}", 0

    def stop(self):
        """Stop the server."""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
            print("[server] Stopped")


# ── Ollama Judge ────────────────────────────────────────────────────────────

class OllamaJudge:
    def __init__(self, model="qwen2.5:7b", url="http://localhost:11434/api/chat"):
        self.model = model
        self.url = url

    def judge(self, question, baseline, candidate, spec=None):
        """Use an LLM to judge which response is better."""
        npc_name = spec.get("npc_name", "the NPC") if spec else "the NPC"
        system_prompt = spec.get("system_prompt", "") if spec else ""
        
        prompt = f"""
You are an expert evaluator of AI NPC dialogue. Your task is to compare two responses from an NPC named '{npc_name}'.

NPC CONTEXT:
System Prompt/Rules: {system_prompt}

EVALUATION CRITERIA:
1. Persona Consistency: Which response best matches the NPC's system prompt, voice, tone, and character? This is the most important factor.
2. Rule Adherence: Which response follows the NPC rules most closely, including the max sentence rule (typically 1-3 sentences), no AI disclaimers, no think tags, and a clear assistant voice?
3. Goal Adherence: Which response answers the player's question correctly and directly?
4. Style Preference: When both answers are factually acceptable, prefer the one that is concise, on-topic, and feels like a short NPC reply rather than a verbose generic answer.
5. Engagement: Is the response encouraging and helpful without being overly wordy?

EXCHANGE:
Player Question: "{question}"

RESPONSE A (Baseline): "{baseline}"
RESPONSE B (Candidate): "{candidate}"

Which response is better? 
FORMAT: Return ONLY a JSON object with:
{{
  "winner": "A" or "B" or "tie",
  "reasoning": "brief explanation",
  "scores": {{ "A": 1-10, "B": 1-10 }}
}}
"""
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0.2}
        }
        try:
            res = requests.post(self.url, json=payload, timeout=60)
            data = res.json()
            raw_content = data["message"]["content"].strip()
            # Extract JSON
            json_match = re.search(r'\{.*\}', raw_content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
        except Exception as e:
            print(f"  [warn] Judge failed: {e}")
        return None


# ── Evaluation logic ────────────────────────────────────────────────────────

def load_subject_spec(spec_path):
    """Load a subject spec JSON file."""
    with open(spec_path) as f:
        return json.load(f)


def load_validation_set(val_path):
    """Load a validation JSONL file and extract questions."""
    questions = []
    with open(val_path) as f:
        for line in f:
            if line.strip():
                example = json.loads(line)
                messages = example.get("messages", [])
                # Find the user message (last user before assistant)
                user_msg = None
                assistant_msg = None
                for msg in messages:
                    if msg["role"] == "user":
                        user_msg = msg["content"]
                    elif msg["role"] == "assistant":
                        assistant_msg = msg["content"]
                if user_msg and assistant_msg:
                    questions.append({
                        "question": user_msg,
                        "expected": assistant_msg,
                        "metadata": example.get("metadata", {}),
                    })
    return questions


def extract_questions_from_spec(spec, val_path=None):
    """Extract eval questions from a spec's validation set or generate from spec."""
    if val_path and os.path.exists(val_path):
        return load_validation_set(val_path)
    return []


def autodetect_validation_path(npc_key):
    """Find the canonical validation file for an NPC."""
    detected = paths.autodetect_dataset(npc_key)
    if detected:
        _, _, val_path = detected
        if val_path.exists():
            return val_path
    return None


def generic_eval_questions(spec=None):
    """Build generic fallback questions from the spec subject instead of chemistry defaults."""
    subject = spec.get("subject", "your subject") if spec else "your subject"
    return [
        {"question": "Who are you?"},
        {"question": "What is your name?"},
        {"question": f"What are the basics of {subject}?"},
        {"question": f"Why is {subject} important?"},
        {"question": f"Give me a simple example from {subject}."},
        {"question": f"What is a common mistake when learning {subject}?"},
        {"question": f"Can you quiz me about {subject}?"},
        {"question": "What should I study next?"},
    ]


def evaluate_model(server, questions, spec=None):
    """Run a model through a set of eval questions and score the responses."""
    results = []
    for i, q in enumerate(questions):
        question = q["question"] if isinstance(q, dict) else q
        expected = q.get("expected") if isinstance(q, dict) else None

        messages = [{"role": "user", "content": question}]
        if spec and spec.get("system_prompt"):
            messages = [
                {"role": "system", "content": spec["system_prompt"]},
                {"role": "user", "content": question},
            ]

        response, latency = server.query(messages)

        metrics = diversity_score(response)
        metrics["latency"] = round(latency, 2)
        metrics["quality"] = quality_estimate(response)

        # Constraint checks
        sent_ok, sent_count = check_sentence_count(response)
        metrics["sentences"] = sent_count
        metrics["sentences_ok"] = sent_ok

        if spec and identity_prompt_requires_name(question):
            name_ok, name_count = check_contains_name(response, spec.get("npc_name"))
            metrics["name_mentions"] = name_count
            metrics["name_ok"] = name_ok
        else:
            metrics["name_mentions"] = 0
            metrics["name_ok"] = True

        ai_ok, ai_pattern = check_no_ai_disclaimer(response)
        metrics["no_ai_disclaimer"] = ai_ok
        metrics["ai_pattern"] = ai_pattern

        metrics["has_think_tags"] = " response" in response

        results.append({
            "question": question,
            "expected": expected,
            "response": response,
            "metrics": metrics,
            "metadata": q.get("metadata", {}) if isinstance(q, dict) else {},
        })

    return results


def compare_models(baseline_results, candidate_results, spec=None, judge=None):
    """Compare two sets of evaluation results and determine winners."""
    comparisons = []
    baseline_wins = 0
    candidate_wins = 0
    ties = 0

    for b, c in zip(baseline_results, candidate_results):
        question = b["question"]
        comparison = {
            "question": question,
            "baseline": b["response"],
            "candidate": c["response"],
            "baseline_metrics": b["metrics"],
            "candidate_metrics": c["metrics"],
            "metadata": b.get("metadata", {}),
            "winner": "tie",
            "reasoning": "Heuristic match"
        }
        expected = b.get("expected") or c.get("expected")

        # ── LLM Judge (if available) ────────────────────────────────────────
        judge_res = None
        if judge:
            print(f"  [judge] Evaluating: {question[:40]}...")
            judge_res = judge.judge(question, b["response"], c["response"], spec)
            if judge_res:
                comparison["judge_scores"] = judge_res.get("scores")
                comparison["reasoning"] = judge_res.get("reasoning")
                winner = judge_res.get("winner", "tie")
                if winner == "A":
                    comparison["winner"] = "baseline"
                elif winner == "B":
                    comparison["winner"] = "candidate"
                else:
                    comparison["winner"] = "tie"
        
        # ── Heuristic fallback/override if no judge or tie ──────────────────
        if comparison["winner"] == "tie":
            # Determine winner based on hard constraints and subject specificity.
            # Name mention is prompt-aware; normal teaching answers are not
            # penalized for omitting the NPC name.
            b_score = 0
            c_score = 0
            
            if b["metrics"].get("sentences_ok", True): b_score += 1
            if c["metrics"].get("sentences_ok", True): c_score += 1
            if b["metrics"].get("name_ok", True): b_score += 1
            if c["metrics"].get("name_ok", True): c_score += 1
            if b["metrics"].get("no_ai_disclaimer", True): b_score += 1
            if c["metrics"].get("no_ai_disclaimer", True): c_score += 1

            b_specificity = response_specificity_score(b["response"], spec=spec, expected=expected)
            c_specificity = response_specificity_score(c["response"], spec=spec, expected=expected)
            comparison["specificity_scores"] = {"baseline": b_specificity, "candidate": c_specificity}
            if b_specificity - c_specificity >= 3:
                b_score += 2
            elif c_specificity - b_specificity >= 3:
                c_score += 2

            if b_score > c_score:
                comparison["winner"] = "baseline"
                comparison["reasoning"] = "Heuristic: constraints plus stronger specificity"
            elif c_score > b_score:
                comparison["winner"] = "candidate"
                comparison["reasoning"] = "Heuristic: constraints plus stronger specificity"

        if comparison["winner"] == "baseline":
            baseline_wins += 1
        elif comparison["winner"] == "candidate":
            candidate_wins += 1
        else:
            ties += 1

        comparisons.append(comparison)

    return {
        "comparisons": comparisons,
        "baseline_wins": baseline_wins,
        "candidate_wins": candidate_wins,
        "ties": ties,
        "total": len(comparisons),
    }


def generate_report(comparison_result, baseline_name="baseline", candidate_name="candidate",
                    spec=None, output_path=None):
    """Generate a markdown evaluation report."""
    output = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    output.append("# NPC Evaluation Report\n")
    output.append(f"- **Date:** {now}")
    output.append(f"- **Mode:** side-by-side")
    if spec:
        output.append(f"- **NPC:** {spec.get('npc_name', 'Unknown')}")
    output.append(f"- **Baseline:** {baseline_name}")
    output.append(f"- **Candidate:** {candidate_name}")
    output.append(f"- **Examples:** {comparison_result['total']}\n")

    # Individual comparisons
    for i, comp in enumerate(comparison_result["comparisons"], 1):
        q = comp["question"]
        b = comp["baseline"]
        c = comp["candidate"]
        bm = comp["baseline_metrics"]
        cm = comp["candidate_metrics"]
        winner = comp["winner"]

        output.append(f"### {i}. {q}\n")
        output.append(f"**Baseline:** {b}\n")
        output.append(f"**Candidate:** {c}\n")

        # Constraints checked
        constraints = []
        if not bm.get("sentences_ok", True):
            constraints.append("sentence_count")
        if not cm.get("sentences_ok", True):
            constraints.append("sentence_count_candidate")
        if not bm.get("name_ok", True):
            constraints.append("has_name")
        if not cm.get("name_ok", True):
            constraints.append("has_name_candidate")
        if constraints:
            output.append(f"**Constraint violations:** {', '.join(constraints)}\n")

        output.append(f"**Metrics:**")
        output.append(f"  - B: words={bm['length']}, sent={bm['sentences']}, "
                      f"name={'Y' if bm.get('name_ok') else 'N'}, "
                      f"think={'Y' if bm.get('has_think_tags') else 'N'}, "
                      f"qual={bm['quality']}")
        output.append(f"  - C: words={cm['length']}, sent={cm['sentences']}, "
                      f"name={'Y' if cm.get('name_ok') else 'N'}, "
                      f"think={'Y' if cm.get('has_think_tags') else 'N'}, "
                      f"qual={cm['quality']}")
        output.append(f"")
        output.append(f"**Winner:** {winner}\n")
        if comp.get("reasoning"):
            output.append(f"**Reasoning:** {comp['reasoning']}\n")

    # Summary
    total = comparison_result["total"]
    bw = comparison_result["baseline_wins"]
    cw = comparison_result["candidate_wins"]
    ties = comparison_result["ties"]

    output.append("## Summary\n")
    output.append(f"| Metric | Value |")
    output.append(f"| ------ | ----- |")
    output.append(f"| Total examples | {total} |")
    output.append(f"| Baseline wins | {bw} |")
    output.append(f"| Candidate wins | {cw} |")
    output.append(f"| Ties | {ties} |")
    output.append(f"| Failure count | 0 |")
    output.append(f"| Candidate win rate | {cw/total*100:.0f}% |\n")

    # Overall comparison table
    output.append("## Overall Comparison Table\n")
    header = f"| # | Question | Baseline ({baseline_name}) | Candidate ({candidate_name}) | Winner |"
    sep = "|---|----------|-------------------------|---------------------------|--------|"
    output.append(header)
    output.append(sep)
    for i, comp in enumerate(comparison_result["comparisons"], 1):
        q_short = comp["question"][:50].replace("|", "/")
        b_short = comp["baseline"][:60].replace("|", "/").replace("\n", " ")
        c_short = comp["candidate"][:60].replace("|", "/").replace("\n", " ")
        output.append(f"| {i} | {q_short}... | {b_short}... | {c_short}... | {comp['winner']} |")

    # Aggregate metrics
    output.append("\n## Detailed Metrics\n")

    b_metrics = [c["baseline_metrics"] for c in comparison_result["comparisons"]]
    c_metrics = [c["candidate_metrics"] for c in comparison_result["comparisons"]]

    for label, metrics_list in [("Baseline", b_metrics), ("Candidate", c_metrics)]:
        avg_sent = sum(m["sentences"] for m in metrics_list) / len(metrics_list)
        avg_words = sum(m["length"] for m in metrics_list) / len(metrics_list)
        avg_qual = sum(m["quality"] for m in metrics_list) / len(metrics_list)
        has_name_count = sum(1 for m in metrics_list if m.get("name_ok"))
        has_think_count = sum(1 for m in metrics_list if m.get("has_think_tags"))

        output.append(f"### {label}\n")
        output.append(f"- Avg sentence count: {avg_sent:.1f}")
        output.append(f"- Avg word count: {avg_words:.0f}")
        output.append(f"- Avg quality score: {avg_qual:.1f}")
        output.append(f"- Contains name: {has_name_count}/{len(metrics_list)}")
        output.append(f"- Has think tags: {has_think_count}/{len(metrics_list)}")
        output.append("")

    report = "\n".join(output)

    if output_path:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w") as f:
            f.write(report)
        print(f"\nReport saved to: {output_file}")

    return report


def generate_html_report(comparison_result, baseline_name="baseline", candidate_name="candidate",
                         spec=None, output_path=None):
    """Generate an HTML evaluation report with embedded loss curves."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    npc_name = spec.get("npc_name", "Unknown") if spec else "Unknown"
    
    # Aggregate metrics
    total = comparison_result["total"]
    bw = comparison_result["baseline_wins"]
    cw = comparison_result["candidate_wins"]
    ties = comparison_result["ties"]
    win_rate = cw / total * 100 if total > 0 else 0
    
    b_metrics = [c["baseline_metrics"] for c in comparison_result["comparisons"]]
    c_metrics = [c["candidate_metrics"] for c in comparison_result["comparisons"]]
    
    avg_b_qual = sum(m["quality"] for m in b_metrics) / len(b_metrics) if b_metrics else 0
    avg_c_qual = sum(m["quality"] for m in c_metrics) / len(c_metrics) if c_metrics else 0
    avg_b_words = sum(m["length"] for m in b_metrics) / len(b_metrics) if b_metrics else 0
    avg_c_words = sum(m["length"] for m in c_metrics) / len(c_metrics) if c_metrics else 0
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Evaluation Report: {npc_name}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f5f5; color: #333; }}
  h1 {{ color: #1a1a2e; border-bottom: 2px solid #e94560; padding-bottom: 10px; }}
  h2 {{ color: #16213e; margin-top: 30px; }}
  .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }}
  .card {{ background: white; border-radius: 8px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
  .card h3 {{ margin: 0 0 5px 0; font-size: 14px; color: #666; text-transform: uppercase; }}
  .card .value {{ font-size: 28px; font-weight: bold; color: #1a1a2e; }}
  .card .winner {{ color: #2ecc71; }}
  .card .loser {{ color: #e74c3c; }}
  table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
  th {{ background: #16213e; color: white; padding: 12px; text-align: left; }}
  td {{ padding: 10px 12px; border-bottom: 1px solid #eee; }}
  tr:hover {{ background: #f0f0f0; }}
  .chart-container {{ background: white; border-radius: 8px; padding: 20px; margin: 20px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
  .constraint-ok {{ color: #2ecc71; }}
  .constraint-fail {{ color: #e74c3c; }}
  .meta {{ color: #666; font-size: 14px; }}
</style>
</head>
<body>
<h1>NPC Evaluation Report: {npc_name}</h1>
<p class="meta">Generated: {now} | Baseline: {baseline_name} | Candidate: {candidate_name}</p>

<div class="summary">
  <div class="card">
    <h3>Total Examples</h3>
    <div class="value">{total}</div>
  </div>
  <div class="card">
    <h3>Candidate Wins</h3>
    <div class="value {'winner' if win_rate >= 50 else 'loser'}">{cw}/{total}</div>
  </div>
  <div class="card">
    <h3>Win Rate</h3>
    <div class="value {'winner' if win_rate >= 50 else 'loser'}">{win_rate:.0f}%</div>
  </div>
  <div class="card">
    <h3>Ties</h3>
    <div class="value">{ties}</div>
  </div>
</div>

<h2>Metrics Comparison</h2>
<div class="chart-container">
  <canvas id="metricsChart"></canvas>
</div>

<h2>Quality Distribution</h2>
<div class="chart-container">
  <canvas id="qualityChart"></canvas>
</div>

<h2>Detailed Results</h2>
<table>
<tr>
  <th>#</th>
  <th>Question</th>
  <th>Baseline Qual</th>
  <th>Candidate Qual</th>
  <th>Winner</th>
</tr>
"""
    
    for i, comp in enumerate(comparison_result["comparisons"], 1):
        q = comp["question"][:80]
        bm = comp["baseline_metrics"]
        cm = comp["candidate_metrics"]
        winner_class = "winner" if comp["winner"] == "candidate" else ("loser" if comp["winner"] == "baseline" else "")
        html += f"""<tr>
  <td>{i}</td>
  <td>{q}</td>
  <td>{bm.get('quality', 'N/A')}</td>
  <td>{cm.get('quality', 'N/A')}</td>
  <td class="{winner_class}">{comp['winner']}</td>
</tr>
"""
    
    html += """</table>

<script>
// Metrics comparison chart
new Chart(document.getElementById('metricsChart'), {
  type: 'bar',
  data: {
    labels: ['Quality Score', 'Word Count', 'Sentence Count'],
    datasets: [
"""
    html += f"""      {{
        label: 'Baseline',
        data: [{avg_b_qual:.1f}, {avg_b_words:.0f}, {sum(m['sentences'] for m in b_metrics) / len(b_metrics):.1f}],
        backgroundColor: 'rgba(54, 162, 235, 0.5)',
        borderColor: 'rgba(54, 162, 235, 1)',
        borderWidth: 1
      }},
      {{
        label: 'Candidate',
        data: [{avg_c_qual:.1f}, {avg_c_words:.0f}, {sum(m['sentences'] for m in c_metrics) / len(c_metrics):.1f}],
        backgroundColor: 'rgba(255, 99, 132, 0.5)',
        borderColor: 'rgba(255, 99, 132, 1)',
        borderWidth: 1
      }}
"""
    
    html += """    ]
  },
  options: {
    responsive: true,
    plugins: {
      legend: { position: 'top' },
      title: { display: true, text: 'Aggregate Metrics Comparison' }
    }
  }
});

// Quality distribution chart (per-example quality scores)
new Chart(document.getElementById('qualityChart'), {
  type: 'scatter',
  data: {
    datasets: [
"""
    b_qual_data = [(i+1, m["quality"]) for i, m in enumerate(b_metrics)]
    c_qual_data = [(i+1, m["quality"]) for i, m in enumerate(c_metrics)]
    
    html += f"""      {{
        label: 'Baseline',
        data: {json.dumps(b_qual_data)},
        backgroundColor: 'rgba(54, 162, 235, 0.5)',
      }},
      {{
        label: 'Candidate',
        data: {json.dumps(c_qual_data)},
        backgroundColor: 'rgba(255, 99, 132, 0.5)',
      }}
"""
    
    html += """    ]
  },
  options: {
    responsive: true,
    plugins: {
      legend: { position: 'top' },
      title: { display: true, text: 'Per-Example Quality Scores' }
    },
    scales: {
      x: { title: { display: true, text: 'Example #' } },
      y: { title: { display: true, text: 'Quality Score' } }
    }
  }
});
</script>
</body>
</html>"""
    
    if output_path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w") as f:
            f.write(html)
        print(f"HTML report saved to: {output}")
    
    return html


def extract_training_metrics(runs_dir=None, npc_key=None):
    """Extract training loss from TensorBoard event files.

    Provide either a runs_dir directly, or an npc_key to look in
    outputs/{npc_key}/runs/.
    """
    if runs_dir is not None:
        runs_dir = Path(runs_dir)
    elif npc_key is not None:
        runs_dir = paths.output_dir(npc_key) / "runs"
    else:
        print("Error: provide --npc-key or a runs directory to extract training metrics")
        return

    if not runs_dir.exists():
        print(f"No runs directory found at {runs_dir}")
        return

    try:
        from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    except ImportError:
        print("TensorBoard not installed. Install with: pip install tensorboard")
        return

    import glob

    print(f"\n{'=' * 60}")
    print(f"  TRAINING METRICS")
    print(f"{'=' * 60}")

    for run_path in sorted(glob.glob(f"{runs_dir}/*/")):
        name = Path(run_path.rstrip("/")).name
        event_files = glob.glob(f"{run_path}/events.out.tfevents.*")
        if not event_files:
            continue

        print(f"\n  Run: {name}")
        try:
            ea = EventAccumulator(run_path)
            ea.Reload()
            tags = ea.Tags()

            for tag in tags.get("scalars", []):
                events = ea.Scalars(tag)
                if events:
                    final = events[-1].value
                    best = min(e.value for e in events)
                    perp = math.exp(final) if final > 0 else 999
                    print(f"    {tag}:")
                    print(f"      steps:    {len(events)}")
                    print(f"      final:    {final:.4f}")
                    print(f"      best:     {best:.4f}")
                    print(f"      perplex:  {perp:.2f}")
        except Exception as e:
            print(f"    Error: {e}")

    # Save structured metrics to eval/training-metrics/{npc_key}.yaml if npc_key is provided
    if npc_key:
        try:
            import yaml
        except ImportError:
            print("Warning: pyyaml not installed, skipping structured YAML output")
            print("Install with: pip install pyyaml")
            return
        
        metrics_yaml = {"runs": {}}
        for run_path in sorted(glob.glob(f"{runs_dir}/*/")):
            name = Path(run_path.rstrip("/")).name
            event_files = glob.glob(f"{run_path}/events.out.tfevents.*")
            if not event_files:
                continue
            metrics_yaml["runs"][name] = {}
            try:
                ea = EventAccumulator(run_path)
                ea.Reload()
                for tag in ea.Tags().get("scalars", []):
                    events = ea.Scalars(tag)
                    if events:
                        metrics_yaml["runs"][name][tag] = {
                            "final": round(events[-1].value, 4),
                            "best": round(min(e.value for e in events), 4),
                            "steps": len(events),
                        }
            except Exception as e:
                metrics_yaml["runs"][name]["_error"] = str(e)
        
        metrics_path = paths.eval_training_metrics_path(npc_key)
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        with open(metrics_path, "w") as f:
            yaml.dump(metrics_yaml, f, default_flow_style=False)
        print(f"\nStructured metrics saved to: {metrics_path}")


def interactive_eval(gguf_path):
    """Interactive mode: chat with a model via llama.cpp server."""
    server = LlamaServer(gguf_path)
    if not server.start():
        print("Failed to start llama-server.")
        return

    print(f"\nInteractive evaluation. Type your prompts. Ctrl+C to exit.\n")
    try:
        while True:
            prompt = input("> ").strip()
            if not prompt:
                continue
            messages = [{"role": "user", "content": prompt}]
            response, latency = server.query(messages)
            print(f"\n{response}\n")
            div = diversity_score(response)
            qual = quality_estimate(response)
            print(f"  [len={div['length']} | {latency:.1f}s | ttr={div['ttr']:.1%} | qual={qual:.1f}]\n")
    except KeyboardInterrupt:
        print()
    finally:
        server.stop()


def main():
    parser = argparse.ArgumentParser(description="Model evaluation and comparison")

    # Mode
    parser.add_argument("--baseline", help="Baseline GGUF model path")
    parser.add_argument("--candidate", help="Candidate GGUF model path")
    parser.add_argument("--model", "-m", help="Single model GGUF path (for interactive or metrics)")

    # Data
    parser.add_argument("--spec", "-s", help="Subject spec JSON (for eval questions)")
    parser.add_argument("--val-data", help="Validation JSONL (held-out questions)")
    parser.add_argument("--num-questions", type=int, default=10,
                        help="Number of eval questions (default: 10)")

    # Output
    parser.add_argument("--output", "-o", help="Output report path")
    parser.add_argument("--report-html", action="store_true",
                        help="Generate HTML report with loss curves")
    parser.add_argument("--track", action="store_true",
                        help="Save results to eval/results/eval_results.jsonl")

    # Modes
    parser.add_argument("--interactive", "-i", action="store_true",
                        help="Interactive chat mode")
    parser.add_argument("--training-metrics", nargs="?", const="",
                        help="Show training metrics from TensorBoard logs")
    parser.add_argument("--npc-key", help="NPC key for per-model TensorBoard runs lookup")

    # Server
    parser.add_argument("--port", type=int, default=8888,
                        help="llama-server port (default: 8888)")
    parser.add_argument("--host", default="127.0.0.1",
                        help="llama-server host (default: 127.0.0.1)")
    parser.add_argument("--gpu-layers", type=int, default=99,
                        help="Number of model layers to offload to GPU for llama-server; use 0 for CPU-only fallback (default: 99)")
    parser.add_argument("--max-tokens", type=int, default=256,
                        help="Maximum generated tokens per eval answer (default: 256)")
    
    # Judge
    parser.add_argument("--judge", action="store_true", help="Use local Ollama judge")
    parser.add_argument("--judge-model", default="qwen2.5:7b", help="Judge model")

    # W&B
    parser.add_argument("--wandb", action="store_true", help="Enable W&B evaluation tracking")
    parser.add_argument("--wandb-project", default="unsloth-core", help="W&B project (default: unsloth-core)")
    parser.add_argument("--wandb-entity", default=None, help="W&B entity (default: auto-detect)")

    # Feedback loop
    parser.add_argument("--feedback-json", help="Save structured per-concept eval results to this JSON file for the feedback loop")

    # LoRA mode (evaluate adapter GGUFs without full-merge)
    parser.add_argument("--base-model", help="Base GGUF model path (required when --candidate is a LoRA adapter)")
    parser.add_argument("--lora-weight", type=float, default=1.0,
                        help="LoRA adapter weight (default: 1.0)")

    args = parser.parse_args()

    # Training metrics mode
    if args.training_metrics is not None:
        runs_dir = args.training_metrics if args.training_metrics else None
        extract_training_metrics(runs_dir=runs_dir, npc_key=args.npc_key)
        return

    # Interactive mode
    if args.interactive:
        if not args.model:
            print("Error: --model required for interactive mode")
            sys.exit(1)
        interactive_eval(args.model)
        return

    # Comparison mode
    if not args.baseline or not args.candidate:
        parser.print_help()
        print("\nError: Both --baseline and --candidate are required for comparison mode.")
        sys.exit(1)

    # Resolve GGUF paths (support glob patterns)
    baseline_paths = list(Path.cwd().glob(args.baseline)) if "*" in args.baseline else [Path(args.baseline)]
    candidate_paths = list(Path.cwd().glob(args.candidate)) if "*" in args.candidate else [Path(args.candidate)]

    if not baseline_paths:
        print(f"Error: Baseline not found: {args.baseline}")
        sys.exit(1)
    if not candidate_paths:
        print(f"Error: Candidate not found: {args.candidate}")
        sys.exit(1)

    baseline_gguf = baseline_paths[0]
    candidate_gguf = candidate_paths[0]

    print(f"Baseline:  {baseline_gguf}")
    print(f"Candidate: {candidate_gguf}")

    # Load questions
    spec = None
    questions = []

    if args.spec:
        spec = load_subject_spec(args.spec)
        npc_key = spec['npc_key']
        val_path = autodetect_validation_path(npc_key)
        questions = extract_questions_from_spec(spec, val_path=str(val_path) if val_path else None)
        print(f"Loaded {len(questions)} eval questions from spec validation set")

        # Default report path to eval/reports/{npc_key}/ if not specified
        if not args.output and spec:
            report_dir = paths.eval_report_dir(spec['npc_key'])
            report_dir.mkdir(parents=True, exist_ok=True)
            args.output = str(paths.eval_report_path(spec['npc_key']))
        if not args.feedback_json and spec:
            args.feedback_json = str(paths.eval_feedback_path(spec['npc_key']))

    if not questions and args.val_data:
        val_set = load_validation_set(args.val_data)
        questions = val_set
        print(f"Loaded {len(questions)} questions from validation set")

    if not questions:
        # Fall back to generic questions
        print("No validation set found. Using generic evaluation questions.")
        questions = generic_eval_questions(spec)

    # Limit questions
    questions = questions[:args.num_questions]

    # Start baseline server
    print("\n[1/4] Starting baseline server...")
    baseline_kwargs = dict(port=args.port, gpu_layers=args.gpu_layers, max_tokens=args.max_tokens)
    if args.base_model:
        base_model_path = Path(args.base_model)
        if not base_model_path.exists():
            print(f"Error: Base model not found: {args.base_model}")
            sys.exit(1)
        if baseline_gguf.resolve() == base_model_path.resolve():
            baseline_server = LlamaServer(base_model_path, **baseline_kwargs)
            print(f"  (LoRA mode: baseline is base-only: {base_model_path})")
        else:
            baseline_server = LlamaServer(
                base_model_path, lora_path=baseline_gguf,
                lora_weight=args.lora_weight, **baseline_kwargs
            )
            print(f"  (LoRA mode: base={base_model_path}, adapter={baseline_gguf})")
    else:
        baseline_server = LlamaServer(baseline_gguf, **baseline_kwargs)
    if not baseline_server.start():
        sys.exit(1)

    print("[2/4] Evaluating baseline...")
    baseline_results = evaluate_model(baseline_server, questions, spec)
    baseline_server.stop()

    # Start candidate server
    print("\n[3/4] Starting candidate server...")
    candidate_kwargs = dict(port=args.port + 1, gpu_layers=args.gpu_layers, max_tokens=args.max_tokens)
    if args.base_model:
        # LoRA mode: candidate is an adapter, start server with base model + --lora
        base_model_path = Path(args.base_model)
        if not base_model_path.exists():
            print(f"Error: Base model not found: {args.base_model}")
            sys.exit(1)
        candidate_server = LlamaServer(
            base_model_path, lora_path=candidate_gguf,
            lora_weight=args.lora_weight, **candidate_kwargs
        )
        print(f"  (LoRA mode: base={base_model_path}, adapter={candidate_gguf})")
    else:
        candidate_server = LlamaServer(candidate_gguf, **candidate_kwargs)
    if not candidate_server.start():
        sys.exit(1)

    print("[4/4] Evaluating candidate...")
    candidate_results = evaluate_model(candidate_server, questions, spec)
    candidate_server.stop()

    # Compare and report
    print("\nComparing models...")
    judge = None
    if args.judge:
        print(f"Initializing Ollama judge ({args.judge_model})...")
        judge = OllamaJudge(model=args.judge_model)

    comparison = compare_models(baseline_results, candidate_results, spec, judge=judge)

    if not "*" in args.baseline:
        baseline_path = Path(args.baseline)
        baseline_name = f"{baseline_path.parent.name}/{baseline_path.stem}"
    else:
        baseline_path = Path(str(baseline_gguf))
        baseline_name = f"{baseline_path.parent.name}/{baseline_path.stem}"
    if not "*" in args.candidate:
        candidate_path = Path(args.candidate)
        candidate_name = f"{candidate_path.parent.name}/{candidate_path.stem}"
    else:
        candidate_path = Path(str(candidate_gguf))
        candidate_name = f"{candidate_path.parent.name}/{candidate_path.stem}"

    report = generate_report(
        comparison,
        baseline_name=baseline_name,
        candidate_name=candidate_name,
        spec=spec,
        output_path=args.output,
    )

    print(report)

    # Generate HTML report with loss curves if requested
    if args.report_html:
        html_path = Path(args.output).with_suffix(".html") if args.output else None
        if html_path is None and spec:
            html_path = paths.eval_report_path(spec["npc_key"], fmt="html")
        generate_html_report(
            comparison,
            baseline_name=baseline_name,
            candidate_name=candidate_name,
            spec=spec,
            output_path=str(html_path) if html_path else None,
        )

    # Track results if requested
    if args.track and spec:
        from scripts.track_eval_results import track_result, track_per_example_result
        
        npc_key = spec.get("npc_key", "unknown")
        cw = comparison["candidate_wins"]
        total = comparison["total"]
        ties = comparison["ties"]
        
        c_metrics_agg = [c["candidate_metrics"] for c in comparison.get("comparisons", [])]
        avg_candidate_quality = sum(m.get("quality", 0) for m in c_metrics_agg) / len(c_metrics_agg) if c_metrics_agg else 0
        
        print(f"\n[track] Storing summary in Supabase/local...")
        track_result(
            npc_key=npc_key,
            model_path=str(candidate_gguf),
            win_rate=cw / total if total > 0 else 0,
            avg_quality=avg_candidate_quality,
            notes=f"vs {baseline_name}: {cw}/{total} wins, {ties} ties",
            metadata={
                "baseline_model": baseline_name,
                "candidate_model": candidate_name,
                "total_examples": total,
                "wins": cw,
                "ties": ties
            }
        )

        print(f"[track] Storing per-example results in Supabase...")
        test_run_name = f"Compare_{npc_key}_{datetime.now().strftime('%Y%m%d_%H%M')}"
        for comp in comparison.get("comparisons", []):
            track_per_example_result(
                npc_key=npc_key,
                test_name=test_run_name,
                prompt=comp["question"],
                response=comp["candidate"],
                expected=None,
                score=1.0 if comp["winner"] == "candidate" else (0.5 if comp["winner"] == "tie" else 0.0),
                metrics=comp["candidate_metrics"],
                metadata={
                    "baseline_response": comp["baseline"],
                    "winner": comp["winner"],
                    "reasoning": comp.get("reasoning")
                }
            )

    # ── Feedback JSON output ────────────────────────────────────────────
    if args.feedback_json and spec:
        npc_key = spec.get("npc_key", "unknown")
        feedback_path = Path(args.feedback_json)
        feedback_path.parent.mkdir(parents=True, exist_ok=True)

        # Group comparisons by concept (extracted from question or use generic)
        from collections import defaultdict
        by_concept = defaultdict(list)
        for comp in comparison.get("comparisons", []):
            concept = "general"
            # Try to extract concept from metadata in the validation question
            q_meta = comp.get("metadata", {})
            if q_meta.get("category"):
                concept = f"{q_meta['category']}/{q_meta.get('concept', 'general')}"
            by_concept[concept].append(comp)

        # Compute per-concept metrics
        per_concept = {}
        for concept, comps in by_concept.items():
            b_metrics = [c["baseline_metrics"] for c in comps]
            c_metrics = [c["candidate_metrics"] for c in comps]
            baseline_wins = sum(1 for c in comps if c["winner"] == "baseline")
            candidate_wins = sum(1 for c in comps if c["winner"] == "candidate")
            ties = sum(1 for c in comps if c["winner"] == "tie")

            per_concept[concept] = {
                "total": len(comps),
                "baseline_wins": baseline_wins,
                "candidate_wins": candidate_wins,
                "ties": ties,
                "win_rate": candidate_wins / len(comps) if comps else 0,
                "avg_baseline_quality": sum(m.get("quality", 0) for m in b_metrics) / len(b_metrics) if b_metrics else 0,
                "avg_candidate_quality": sum(m.get("quality", 0) for m in c_metrics) / len(c_metrics) if c_metrics else 0,
                "constraint_violations": sum(
                    1 for c in comps
                    if not c["candidate_metrics"].get("sentences_ok", True)
                    or not c["candidate_metrics"].get("no_ai_disclaimer", True)
                ),
                "examples": [{
                    "question": c["question"],
                    "winner": c["winner"],
                    "candidate_quality": c["candidate_metrics"].get("quality", 0),
                    "candidate_words": c["candidate_metrics"].get("length", 0),
                    "sentences_ok": c["candidate_metrics"].get("sentences_ok", True),
                    "no_ai_disclaimer": c["candidate_metrics"].get("no_ai_disclaimer", True),
                } for c in comps],
            }

        feedback_data = {
            "npc_key": npc_key,
            "baseline": baseline_name,
            "candidate": candidate_name,
            "total_examples": comparison["total"],
            "baseline_wins": comparison["baseline_wins"],
            "candidate_wins": comparison["candidate_wins"],
            "ties": comparison["ties"],
            "win_rate": comparison["candidate_wins"] / comparison["total"] if comparison["total"] > 0 else 0,
            "per_concept": per_concept,
            "weak_concepts": [
                concept for concept, data in per_concept.items()
                if data["win_rate"] < 0.5 or data["avg_candidate_quality"] < 20 or data["constraint_violations"] > 0
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        with open(feedback_path, "w") as f:
            json.dump(feedback_data, f, indent=2)
        print(f"\n[feedback] Structured eval results saved to: {feedback_path}")
        print(f"[feedback] Weak concepts identified: {len(feedback_data['weak_concepts'])}")
        for wc in feedback_data["weak_concepts"]:
            info = per_concept[wc]
            print(f"  - {wc}: win_rate={info['win_rate']:.0%}, avg_quality={info['avg_candidate_quality']:.1f}, violations={info['constraint_violations']}")

    # ── W&B Evaluation Tracking ─────────────────────────────────────────
    if args.wandb and spec:
        import wandb
        npc_key = spec.get("npc_key", "unknown")
        cw = comparison["candidate_wins"]
        bw = comparison["baseline_wins"]
        total = comparison["total"]
        ties = comparison["ties"]
        win_rate = cw / total if total > 0 else 0

        wandb_group_env = os.environ.get("WANDB_GROUP")
        config = {
            "npc_key": npc_key,
            "baseline": baseline_name,
            "candidate": candidate_name,
            "num_questions": total,
            "judge": args.judge,
            "judge_model": args.judge_model,
            "baseline_model_path": args.baseline,
            "candidate_model_path": args.candidate,
            "categories": list(set(
                q.get("metadata", {}).get("category", "general")
                for q in questions
            )),
        }
        if wandb_group_env:
            config["wandb_group"] = wandb_group_env
        wandb.init(
            project=args.wandb_project or "unsloth-core",
            entity=args.wandb_entity,
            group=os.environ.get("WANDB_GROUP"),
            job_type=os.environ.get("WANDB_JOB_TYPE", "eval"),
            config=config,
            name=f"eval-{npc_key}-{baseline_name}-vs-{candidate_name}",
            tags=["eval", npc_key, baseline_name, candidate_name],
        )
        # Log comparison summary
        wandb.log({
            "eval/baseline_wins": bw,
            "eval/candidate_wins": cw,
            "eval/ties": ties,
            "eval/total": total,
            "eval/win_rate": win_rate,
        })
        # Build a W&B Table for structured per-question results
        table_data = []
        for comp in comparison.get("comparisons", []):
            meta = comp.get("metadata", {})
            category = meta.get("category", "general")
            concept = meta.get("concept", "general")
            table_data.append([
                comp["question"],
                category,
                concept,
                comp["baseline_metrics"].get("quality", 0),
                comp["candidate_metrics"].get("quality", 0),
                comp["baseline_metrics"].get("length", 0),
                comp["candidate_metrics"].get("length", 0),
                comp["baseline_metrics"].get("sentences", 0),
                comp["candidate_metrics"].get("sentences", 0),
                comp["baseline_metrics"].get("sentences_ok", True),
                comp["candidate_metrics"].get("sentences_ok", True),
                comp["baseline_metrics"].get("no_ai_disclaimer", True),
                comp["candidate_metrics"].get("no_ai_disclaimer", True),
                comp["winner"],
            ])
        eval_table = wandb.Table(
            columns=[
                "question", "category", "concept",
                "baseline_quality", "candidate_quality",
                "baseline_words", "candidate_words",
                "baseline_sentences", "candidate_sentences",
                "baseline_sentences_ok", "candidate_sentences_ok",
                "baseline_no_ai", "candidate_no_ai",
                "winner",
            ],
            data=table_data,
        )
        wandb.log({"eval/comparison_table": eval_table})
        # Aggregate metrics per category
        from collections import defaultdict
        by_category = defaultdict(list)
        for row in table_data:
            by_category[row[1]].append(row)  # row[1] = category
        for cat, rows in by_category.items():
            cat_wins = sum(1 for r in rows if r[-1] == "candidate")
            cat_total = len(rows)
            wandb.log({
                f"eval/category/{cat}/win_rate": cat_wins / cat_total if cat_total > 0 else 0,
                f"eval/category/{cat}/total": cat_total,
                f"eval/category/{cat}/wins": cat_wins,
            })
        # Log report as artifact
        if args.output and os.path.exists(args.output):
            try:
                report_artifact = wandb.Artifact(
                    name=f"eval-report-{npc_key}",
                    type="eval-report",
                    description=f"Evaluation report for {npc_key}: {baseline_name} vs {candidate_name}",
                    metadata={
                        "baseline": baseline_name,
                        "candidate": candidate_name,
                        "win_rate": win_rate,
                        "total_questions": total,
                    },
                )
                report_artifact.add_file(args.output)
                wandb.log_artifact(report_artifact)
            except Exception as e:
                print(f"  [wandb] Report artifact failed: {e}")
        wandb.finish()


if __name__ == "__main__":
    main()
