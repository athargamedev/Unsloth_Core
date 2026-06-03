# PIPELINE VISUALIZATION REPORT

<style>
:root {
  --background: oklch(0.97 0.005 260);
  --foreground: oklch(0.18 0.02 260);
  --card: oklch(1 0 0);
  --card-foreground: oklch(0.18 0.02 260);
  --primary: oklch(0.50 0.25 280);
  --primary-foreground: oklch(1 0 0);
  --secondary: oklch(0.50 0.18 180);
  --secondary-foreground: oklch(1 0 0);
  --muted: oklch(0.92 0.01 260);
  --muted-foreground: oklch(0.40 0.02 260);
  --accent: oklch(0.60 0.22 50);
  --accent-foreground: oklch(0.18 0.02 260);
  --destructive: oklch(0.50 0.25 25);
  --destructive-foreground: oklch(1 0 0);
  --success: oklch(0.45 0.20 150);
  --success-foreground: oklch(1 0 0);
  --warning: oklch(0.55 0.18 85);
  --warning-foreground: oklch(0.18 0.02 260);
  --border: oklch(0.88 0.01 260);
  --input: oklch(0.92 0.01 260);
  --ring: oklch(0.50 0.25 280);
  --code-bg: oklch(0.92 0.01 260);

  --font-sans: 'Inter', system-ui, -apple-system, sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', ui-monospace, monospace;
  --font-display: ui-serif, Georgia, 'Times New Roman', serif;
  --radius: 0.625rem;
}

@media (prefers-color-scheme: dark) {
  :root {
    --background: oklch(0.15 0.02 260);
    --foreground: oklch(0.90 0.01 260);
    --card: oklch(0.22 0.02 260);
    --card-foreground: oklch(0.90 0.01 260);
    --muted: oklch(0.26 0.02 260);
    --muted-foreground: oklch(0.72 0.02 260);
    --primary: oklch(0.75 0.18 280);
    --primary-foreground: oklch(0.15 0.02 260);
    --accent: oklch(0.70 0.20 60);
    --border: oklch(0.35 0.02 260);
    --code-bg: oklch(0.26 0.02 260);
    --destructive: oklch(0.65 0.20 25);
    --success: oklch(0.72 0.17 150);
    --warning: oklch(0.75 0.15 85);
  }
}

*, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: var(--font-sans);
  background: var(--background);
  color: var(--foreground);
  line-height: 1.65;
  font-size: 15px;
  -webkit-font-smoothing: antialiased;
}

.container {
  max-width: 1080px;
  margin: 0 auto;
  padding: 64px 24px;
}

.eyebrow {
  font-family: var(--font-mono);
  font-size: 0.72rem;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted-foreground);
  display: block;
}

header h1 {
  font-family: var(--font-display);
  font-size: 2.2rem;
  font-weight: 500;
  margin: 8px 0 24px;
  line-height: 1.2;
}

.prompt-box {
  background: var(--muted);
  border: 1.5px solid var(--border);
  border-radius: var(--radius);
  padding: 18px 24px;
  margin-bottom: 40px;
}

.prompt-label {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted-foreground);
  display: block;
  margin-bottom: 6px;
}

.prompt-box p {
  font-size: 0.92rem;
  color: var(--muted-foreground);
  line-height: 1.55;
}

.summary-strip {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin: 32px 0 48px;
}

@media (max-width: 768px) {
  .summary-strip {
    grid-template-columns: repeat(2, 1fr);
  }
}

.stat-card {
  border: 1.5px solid var(--border);
  border-radius: var(--radius);
  padding: 20px 24px;
  text-align: center;
  background: var(--card);
}

.stat-value {
  font-family: var(--font-display);
  font-size: 1.9rem;
  font-weight: 500;
  display: block;
  color: var(--foreground);
}

.stat-label {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted-foreground);
  margin-top: 6px;
  display: block;
}

section { margin-top: 64px; }

.section-header {
  display: flex;
  align-items: baseline;
  gap: 16px;
  margin-bottom: 24px;
  padding-bottom: 8px;
  border-bottom: 1.5px solid var(--border);
}

.section-number {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--primary);
}

.section-header h2 {
  font-family: var(--font-display);
  font-size: 1.4rem;
  font-weight: 500;
}

.code-panel {
  background: var(--code-bg);
  border-radius: var(--radius);
  padding: 24px;
  overflow-x: auto;
  margin: 24px 0;
  border: 1.5px solid var(--border);
}

.code-label {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: var(--muted-foreground);
  display: block;
  margin-bottom: 12px;
}

.code-panel pre {
  margin: 0;
  font-family: var(--font-mono);
  font-size: 0.85rem;
  line-height: 1.55;
  color: var(--foreground);
}

/* Syntax tokens — these use semantic roles, not fixed colors */
.code-panel .kw  { color: var(--primary); font-weight: 600; }         /* keywords */
.code-panel .fn  { color: var(--accent); }           /* identifiers, types */
.code-panel .str { color: var(--success); }          /* strings */
.code-panel .cm  { color: var(--muted-foreground); font-style: italic; } /* comments */
.code-panel .num { color: var(--warning); }          /* numbers */

.diagram-panel {
  border: 1.5px solid var(--border);
  border-radius: var(--radius);
  padding: 24px;
  margin: 32px 0;
  background: var(--card);
}

.diagram-caption {
  font-family: var(--font-mono);
  font-size: 0.72rem;
  color: var(--muted-foreground);
  display: block;
  margin-top: 12px;
  text-align: center;
}

.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}

@media (max-width: 720px) {
  .two-col { grid-template-columns: 1fr; }
}

.milestones { display: flex; flex-direction: column; gap: 0; margin: 32px 0; }

.milestone {
  display: grid;
  grid-template-columns: 120px 28px 1fr;
  gap: 0 18px;
}

.milestone .when {
  text-align: right;
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: var(--muted-foreground);
  padding-top: 4px;
}

.milestone .dot-col { display: flex; flex-direction: column; align-items: center; }

.milestone .dot {
  width: 14px; height: 14px; border-radius: 50%;
  background: var(--card);
  border: 3px solid var(--primary);
  flex-shrink: 0;
}

.milestone .dot.done { background: var(--success); border-color: var(--success); }

.milestone .line { width: 2px; flex: 1; background: var(--border); margin: 4px 0; }
.milestone:last-child .line { display: none; }

.milestone .body { padding-bottom: 36px; }

.milestone .body h3 {
  font-family: var(--font-display);
  font-size: 1.15rem;
  font-weight: 500;
  margin-bottom: 6px;
}

.milestone .body p {
  font-size: 0.9rem;
  color: var(--muted-foreground);
  max-width: 720px;
  margin-bottom: 10px;
  line-height: 1.6;
}

.stage-card {
  background: var(--card);
  border: 1.5px solid var(--border);
  border-radius: var(--radius);
  padding: 24px;
  margin-bottom: 16px;
}

.stage-card h3 {
  font-family: var(--font-display);
  font-size: 1.15rem;
  font-weight: 500;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.stage-card p {
  font-size: 0.92rem;
  color: var(--muted-foreground);
  line-height: 1.6;
}

.badge {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: calc(var(--radius) - 4px);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.badge.success {
  background: color-mix(in oklab, var(--success) 12%, transparent);
  color: var(--success);
}

.badge.primary {
  background: color-mix(in oklab, var(--primary) 12%, transparent);
  color: var(--primary);
}

/* SVG specific styling */
.svg-box {
  fill: var(--card);
  stroke: var(--border);
  stroke-width: 1.5px;
  transition: stroke 0.2s, fill 0.2s;
}

.svg-box.highlight {
  fill: color-mix(in oklab, var(--primary) 8%, var(--card));
  stroke: var(--primary);
}

.svg-box:hover {
  stroke: var(--primary);
}

.svg-text-title {
  font-family: var(--font-sans);
  font-size: 10px;
  font-weight: 600;
  fill: var(--foreground);
}

.svg-text-sub {
  font-family: var(--font-mono);
  font-size: 8.5px;
  fill: var(--muted-foreground);
}

.svg-arrow-line {
  stroke: var(--border);
  stroke-width: 1.5px;
}

.svg-arrow-line.highlight {
  stroke: var(--primary);
}

.svg-edge-label {
  font-family: var(--font-mono);
  font-size: 8px;
  fill: var(--muted-foreground);
  font-weight: 500;
}
</style>

<div class="container">

  <header>
    <span class="eyebrow">UNSLOTH_CORE · PIPELINE DATAFLOW</span>
    <h1>Optimized SFT Training &amp; Evaluation Pipeline</h1>
    <div class="prompt-box">
      <span class="prompt-label">Pipeline Brief</span>
      <p>
        An end-to-end highly-optimized framework designed to fine-tune and evaluate lightweight 3B parameter llama3.2 NPC adapters under local 6GB VRAM hardware boundaries. Integrating automated schema validation, grounded synthetic dialogue generation, non-destructive sanitization, asynchronous parallel DeepEval gating, VRAM-optimized QLoRA training, concurrent dynamic-port llama.cpp server side-by-side evaluations, and semantic BM25 gap detection.
      </p>
    </div>
  </header>

  <div class="summary-strip">
    <div class="stat-card">
      <span class="stat-value">~2.0 Min</span>
      <span class="stat-label">DeepEval Runtime</span>
    </div>
    <div class="stat-card">
      <span class="stat-value">+0.5 GB</span>
      <span class="stat-label">VRAM Saved</span>
    </div>
    <div class="stat-card">
      <span class="stat-value">-1729</span>
      <span class="stat-label">Redundant Lines</span>
    </div>
    <div class="stat-card">
      <span class="stat-value">23 / 23</span>
      <span class="stat-label">Regression Tests</span>
    </div>
  </div>

  <section>
    <div class="section-header">
      <span class="section-number">01</span>
      <h2>Milestone Timeline</h2>
    </div>
    
    <div class="milestones">
      <div class="milestone">
        <div class="when">Phase 1</div>
        <div class="dot-col"><span class="dot done"></span><span class="line"></span></div>
        <div class="body">
          <h3>Validation &amp; Synthesis</h3>
          <p>
            Audit raw character specs against schema models. Invoke grounded synthetic dataset generation using high-quality local Ollama configurations, saving intermediate outputs to structured multi-turn SFT JSONL format.
          </p>
          <div class="tags">
            <span class="tag">spec validation</span>
            <span class="tag">grounded generation</span>
          </div>
        </div>
      </div>

      <div class="milestone">
        <div class="when">Phase 2</div>
        <div class="dot-col"><span class="dot done"></span><span class="line"></span></div>
        <div class="body">
          <h3>Sanitization &amp; Gating</h3>
          <p>
            Scrub conversational boilerplate, strip AI disclaimer markers, and perform sentence-boundary normalization. Inject data into DeepEval Quality Gates operating asynchronous concurrent judges for near-instant validation.
          </p>
          <div class="tags">
            <span class="tag">disclaimer repair</span>
            <span class="tag">asyncio gating</span>
          </div>
        </div>
      </div>

      <div class="milestone">
        <div class="when">Phase 3</div>
        <div class="dot-col"><span class="dot done"></span><span class="line"></span></div>
        <div class="body">
          <h3>High-Performance SFT Training</h3>
          <p>
            Load base models utilizing bitsandbytes 4-bit double quantization. Fine-tune custom character LoRA adapters using packed sequences, optimizing attention maps and memory usage on 6GB VRAM, then exporting to f16 GGUF files.
          </p>
          <div class="tags">
            <span class="tag">double-quant</span>
            <span class="tag">gguf export</span>
          </div>
        </div>
      </div>

      <div class="milestone">
        <div class="when">Phase 4</div>
        <div class="dot-col"><span class="dot"></span><span class="line"></span></div>
        <div class="body">
          <h3>Side-by-Side Runtime &amp; Gap Analysis</h3>
          <p>
            Instantiate concurrent dynamic-port llama.cpp subprocesses. Drive identical evaluation prompt runs against both baseline and candidate models, parse results, and run keyword gap checks to verify correct primer knowledge retention.
          </p>
          <div class="tags">
            <span class="tag">dynamic port</span>
            <span class="tag">bm25 gap checking</span>
          </div>
        </div>
      </div>
    </div>
  </section>

  <section>
    <div class="section-header">
      <span class="section-number">02</span>
      <h2>Pipeline Dataflow</h2>
    </div>

    <div class="diagram-panel">
      <svg viewBox="0 0 1020 300" xmlns="http://www.w3.org/2000/svg" style="width:100%; max-width:1020px">
        <defs>
          <!-- Grid pattern for background -->
          <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">
            <path d="M 20 0 L 0 0 0 20" fill="none" stroke="var(--border)" stroke-width="0.5" opacity="0.3"/>
          </pattern>
          <!-- Custom SVG arrow markers -->
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="var(--muted-foreground)"/>
          </marker>
          <marker id="arrow-primary" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="var(--primary)"/>
          </marker>
          <!-- Subtle box gradients -->
          <linearGradient id="box-grad-primary" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="var(--background)"/>
            <stop offset="100%" stop-color="color-mix(in oklab, var(--primary) 5%, var(--background))"/>
          </linearGradient>
          <linearGradient id="box-grad-accent" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="var(--background)"/>
            <stop offset="100%" stop-color="color-mix(in oklab, var(--accent) 5%, var(--background))"/>
          </linearGradient>
        </defs>

        <!-- Background grid -->
        <rect width="1020" height="300" fill="url(#grid)" rx="10" stroke="var(--border)" stroke-width="1"/>

        <!-- Arrows & Edge Labels -->
        <!-- Node 1 -> Node 2 -->
        <line x1="120" y1="135" x2="142" y2="135" class="svg-arrow-line highlight" marker-end="url(#arrow-primary)"/>
        <text x="135" y="122" text-anchor="middle" class="svg-edge-label" fill="var(--primary)">verify</text>

        <!-- Node 2 -> Node 3 -->
        <line x1="260" y1="135" x2="282" y2="135" class="svg-arrow-line" marker-end="url(#arrow)"/>
        <text x="275" y="122" text-anchor="middle" class="svg-edge-label">ChatML</text>

        <!-- Node 3 -> Node 4 -->
        <line x1="405" y1="135" x2="427" y2="135" class="svg-arrow-line" marker-end="url(#arrow)"/>
        <text x="420" y="122" text-anchor="middle" class="svg-edge-label">clean.jsonl</text>

        <!-- Node 4 -> Node 5 -->
        <line x1="555" y1="135" x2="577" y2="135" class="svg-arrow-line highlight" marker-end="url(#arrow-primary)"/>
        <text x="570" y="122" text-anchor="middle" class="svg-edge-label" fill="var(--primary)">Gate Pass</text>

        <!-- Node 5 -> Node 6 -->
        <line x1="705" y1="135" x2="727" y2="135" class="svg-arrow-line" marker-end="url(#arrow)"/>
        <text x="720" y="122" text-anchor="middle" class="svg-edge-label">GGUF</text>

        <!-- Node 6 -> Node 7 -->
        <line x1="870" y1="135" x2="892" y2="135" class="svg-arrow-line" marker-end="url(#arrow)"/>
        <text x="885" y="122" text-anchor="middle" class="svg-edge-label">feedback</text>

        <!-- Nodes Group -->
        <!-- Node 1: Spec Validation -->
        <g transform="translate(10, 100)">
          <rect width="110" height="70" rx="8" class="svg-box highlight" fill="url(#box-grad-primary)"/>
          <text x="55" y="32" text-anchor="middle" class="svg-text-title">Spec Validation</text>
          <text x="55" y="48" text-anchor="middle" class="svg-text-sub">Schema Auditing</text>
        </g>

        <!-- Node 2: Ollama Generation -->
        <g transform="translate(150, 100)">
          <rect width="110" height="70" rx="8" class="svg-box" />
          <text x="55" y="32" text-anchor="middle" class="svg-text-title">Ollama Gen</text>
          <text x="55" y="48" text-anchor="middle" class="svg-text-sub">Synthetic SFT</text>
        </g>

        <!-- Node 3: Sanitizer & Repair -->
        <g transform="translate(290, 100)">
          <rect width="115" height="70" rx="8" class="svg-box" />
          <text x="57.5" y="32" text-anchor="middle" class="svg-text-title">Sanitizer &amp; Repair</text>
          <text x="57.5" y="48" text-anchor="middle" class="svg-text-sub">Sentence Budget</text>
        </g>

        <!-- Node 4: DeepEval Quality Gate -->
        <g transform="translate(435, 100)">
          <rect width="120" height="70" rx="8" class="svg-box highlight" fill="url(#box-grad-primary)"/>
          <text x="60" y="32" text-anchor="middle" class="svg-text-title">Quality Gate</text>
          <text x="60" y="48" text-anchor="middle" class="svg-text-sub">Asyncio Judges</text>
        </g>

        <!-- Node 5: SFT Trainer (QLoRA) -->
        <g transform="translate(585, 100)">
          <rect width="120" height="70" rx="8" class="svg-box" />
          <text x="60" y="32" text-anchor="middle" class="svg-text-title">SFT Trainer</text>
          <text x="60" y="48" text-anchor="middle" class="svg-text-sub">4-bit QLoRA</text>
        </g>

        <!-- Node 6: LlamaServer Side-by-Side -->
        <g transform="translate(735, 100)">
          <rect width="135" height="70" rx="8" class="svg-box" />
          <text x="67.5" y="32" text-anchor="middle" class="svg-text-title">LlamaServer SbS</text>
          <text x="67.5" y="48" text-anchor="middle" class="svg-text-sub">Concurrent Ports</text>
        </g>

        <!-- Node 7: Local Gap Detector -->
        <g transform="translate(900, 100)">
          <rect width="110" height="70" rx="8" class="svg-box highlight" fill="url(#box-grad-primary)"/>
          <text x="55" y="32" text-anchor="middle" class="svg-text-title">Gap Detector</text>
          <text x="55" y="48" text-anchor="middle" class="svg-text-sub">BM25 Concept</text>
        </g>
      </svg>
      <span class="diagram-caption">7-Stage End-to-End Fine-Tuning &amp; Evaluation Pipeline Dataflow</span>
    </div>
  </section>

  <section>
    <div class="section-header">
      <span class="section-number">03</span>
      <h2>Stage Tour</h2>
    </div>

    <div class="stage-card">
      <h3><span class="badge primary">Stage 1</span> Spec Validation</h3>
      <p>
        The pipeline starts with a comprehensive preflight validation of the subject JSON specification (`subject.json`). It audits required dialogue constraints, verification prompts, and metadata format structures before allowing any downstream generation runs to execute.
      </p>
    </div>

    <div class="stage-card">
      <h3><span class="badge success">Stage 2</span> Ollama Generation</h3>
      <p>
        SFT datasets are generated locally using structured multi-turn templates and the optimized `qwen2.5:7b` local Ollama configuration. Generates high-quality dialogues strictly aligned with character primer guidelines and background reference documentation.
      </p>
    </div>

    <div class="stage-card">
      <h3><span class="badge primary">Stage 3</span> Sanitizer &amp; Repair</h3>
      <p>
        The `sanitize_dataset` stage processes generated multi-turn rows to trim text to precise bubble constraints using strict sentence boundary-finding algorithms. It strips conversational AI filler (e.g. "Certainly! Here is my response...") and repairs malformed dialogue formats non-destructively.
      </p>
    </div>

    <div class="stage-card">
      <h3><span class="badge success">Stage 4</span> DeepEval Quality Gate</h3>
      <p>
        Rather than costly synchronous API calls, the pipeline deploys parallel DeepEval judges running under a customized `ThreadPoolExecutor` and asyncio wrapper, slashing overall dataset evaluation runtime from 10-15 minutes down to under 2.0 minutes while preserving exact judgment scoring.
      </p>
    </div>

    <div class="stage-card">
      <h3><span class="badge primary">Stage 5</span> SFT Trainer (QLoRA)</h3>
      <p>
        Adapters are trained on a RTX 3060 6GB with bitsandbytes 4-bit double-quantization and sequence packing, saving an additional 0.5 GB of crucial VRAM and preventing Out-Of-Memory errors. Upon training completion, the adapter is merged and exported as an f16 GGUF model.
      </p>
    </div>

    <div class="stage-card">
      <h3><span class="badge success">Stage 6</span> LlamaServer Side-by-Side</h3>
      <p>
        Launches dual parallel `llama.cpp` server subprocesses. Uses an intelligent dynamic socket-binding preflight routine to self-discover free ports sequentially (trying up to 20 sockets). Feeds standard evaluation prompts concurrently and records dynamic outputs to `feedback.json`.
      </p>
    </div>

    <div class="stage-card">
      <h3><span class="badge primary">Stage 7</span> Local Gap Detector</h3>
      <p>
        A post-evaluation audit step. Scrapes dialogue responses, indexing core concepts using BM25, and compares keyword coverage directly against the character's primary documentation (`{npc}_primer.md`) to isolate and alert on missing topical coverage gaps.
      </p>
    </div>
  </section>

  <section>
    <div class="section-header">
      <span class="section-number">04</span>
      <h2>Code Highlights</h2>
    </div>

    <div class="code-panel">
      <span class="code-label">src/core/dataset/sanitize_dataset.py</span>
      <pre><code><span class="kw">def</span> <span class="fn">trim_to_max_sentences</span>(text: <span class="fn">str</span>, max_sentences: <span class="fn">int</span>) -> <span class="fn">str</span>:
    <span class="cm">"""Trim text to max_sentences using exact boundary-finding and normalization."""</span>
    <span class="kw">if not</span> text:
        <span class="kw">return</span> <span class="str">""</span>
    <span class="kw">if</span> max_sentences <= <span class="num">0</span>:
        <span class="kw">return</span> <span class="str">""</span>

    <span class="cm"># Replace abbreviations with same-length placeholders to preserve indices</span>
    cleaned = _ABBREVIATIONS_PATTERN.sub(<span class="kw">lambda</span> m: m.group(<span class="num">0</span>).replace(<span class="str">'.'</span>, <span class="str">'\x00'</span>), text)
    cleaned = _INITIALISM_PATTERN.sub(<span class="kw">lambda</span> m: m.group(<span class="num">0</span>).replace(<span class="str">'.'</span>, <span class="str">'\x00'</span>), cleaned)
    cleaned = cleaned.replace(<span class="str">'...'</span>, <span class="str">'\x00\x00\x00'</span>)

    matches = list(re.finditer(<span class="str">r'[.!?]+'</span>, cleaned))

    <span class="kw">if</span> len(matches) < max_sentences:
        trimmed = text.strip()
    <span class="kw">else</span>:
        boundary_match = matches[max_sentences - <span class="num">1</span>]
        trimmed = text[:boundary_match.end()].strip()

    <span class="kw">if</span> trimmed <span class="kw">and not</span> trimmed[-<span class="num">1</span>] <span class="kw">in</span> <span class="str">'.!?'</span>:
        trimmed += <span class="str">'.'</span>

    <span class="kw">return</span> trimmed</code></pre>
    </div>

    <div class="code-panel">
      <span class="code-label">src/core/evaluation/evaluate.py</span>
      <pre><code><span class="kw">def</span> <span class="fn">start</span>(self, timeout=<span class="num">180</span>):
    <span class="cm">"""Start the llama.cpp server and wait until it's ready."""</span>
    <span class="kw">import</span> <span class="fn">socket</span>
    
    original_port = self.port
    checked_ports = <span class="num">0</span>
    max_port_attempts = <span class="num">20</span>
    
    <span class="kw">while</span> checked_ports < max_port_attempts:
        <span class="kw">try</span>:
            <span class="cm"># Attempt to temporarily bind a socket to check if port is free</span>
            <span class="kw">with</span> socket.socket(socket.AF_INET, socket.SOCK_STREAM) <span class="kw">as</span> s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, <span class="num">1</span>)
                s.bind((self.host, self.port))
            <span class="cm"># If successfully bound, port is free!</span>
            <span class="kw">break</span>
        <span class="kw">except</span> (OSError, socket.error) <span class="kw">as</span> e:
            print(<span class="str">f"[server] Warning: Port {self.port} already in use. Trying next..."</span>)
            self.port += <span class="num">1</span>
            checked_ports += <span class="num">1</span>
    <span class="kw">else</span>:
        <span class="kw">raise</span> <span class="fn">RuntimeError</span>(<span class="str">"Could not find free port after 20 attempts"</span>)</code></pre>
    </div>
  </section>

</div>
