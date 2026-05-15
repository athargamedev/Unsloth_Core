"""
constants.py — Named constants for the Unsloth_Core pipeline.

Extracts magic numbers and repeated literals into self-documenting names.
"""

# ── Dataset splitting ─────────────────────────────────────────────────────────
DEFAULT_VAL_SPLIT = 0.12          # Default validation split ratio
MIN_EXAMPLES_FOR_VALIDATION = 5   # Minimum examples needed to create a val split
DEFAULT_SEED = 42                 # Default random seed for reproducibility

# ── Temperature defaults ──────────────────────────────────────────────────────
ONYX_TEMPERATURE = 0.5            # Lower temp for Onyx (factual retrieval)
LLM_GENERATOR_TEMPERATURE = 0.8   # Higher temp for non-Onyx generators (creative)

# ── Onyx context / retrieval ──────────────────────────────────────────────────
DEFAULT_ONYX_CHUNKS = 4           # Max context chunks per query
DEFAULT_ONYX_CONTEXT_CHARS = 1800  # Max context characters per query
DEFAULT_ONYX_QUERIES = 1          # Default query count per category
ONYX_CATEGORY_QUERIES = 3         # Query count for Onyx category generation

# ── Onyx example scoring weights (must sum to 1.0) ────────────────────────────
ONYX_QUALITY_WEIGHTS = {
    "documents": 0.35,
    "context_chunks": 0.20,
    "scores": 0.15,
    "substantive_answer": 0.15,
    "multiple_queries": 0.15,
}
ONYX_SCORE_CLAMP_MIN = 0.0
ONYX_SCORE_CLAMP_MAX = 1.0
ONYX_SCORE_ROUND_DIGITS = 4

# ── Timeouts (seconds) ────────────────────────────────────────────────────────
SUBPROCESS_TIMEOUT = 120          # For onyx tool subprocess calls
API_TIMEOUT = 60                  # For OpenAI / Anthropic API calls

# ── Token / length limits ─────────────────────────────────────────────────────
FIRST_SENTENCE_MAX_CHARS = 220     # _first_sentence() truncation
DEDUP_KEY_PREFIX_LENGTH = 120     # Onyx dedup key prefix length
OLLAMA_MAX_TOKENS = 1024
ANTHROPIC_MAX_TOKENS = 1024
LEARNING_OBJECTIVE_MAX = 2         # Max learning objectives per category
CONCEPT_MAX_WORDS = 5              # Max words per extracted concept
CONCEPT_MIN_WORDS = 3              # Min word-length filter for concepts
MAX_QUESTIONS_PER_PROMPT = 5       # Max questions per prompt in multi-turn

# ── Retry / progress ──────────────────────────────────────────────────────────
QUALITY_FILTER_RETRY_MULTIPLIER = 3  # count * this = max retries
PROGRESS_PRINT_INTERVAL = 5          # Print progress every N examples
ONYX_QUERIES_MIN = 1
ONYX_QUERIES_MAX = 5
ONYX_PREP_PASSES_MIN = 1
ONYX_PREP_PASSES_MAX = 3
ONYX_PREP_SLEEP_MIN = 0.0
ONYX_PREP_SLEEP_MAX = 30.0

# ── Valid multi-turn categories (must have interactive dialogue potential) ─────
MULTI_TURN_CATEGORIES = ["teaching", "dialogue"]

# ── Prompt / string literals ──────────────────────────────────────────────────
DEFAULT_OLLAMA_MODEL = "llama3.1:latest"
DEFAULT_OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_OPENAI_MODEL = "gpt-4o"
DEFAULT_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_ANTHROPIC_MODEL = "claude-3-5-sonnet-20240620"
DEFAULT_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"

# ── Training defaults ─────────────────────────────────────────────────────────
TRAIN_LOG_STEPS = 1
TRAIN_SAVE_TOTAL_LIMIT = 3
TRAIN_DATASET_NUM_PROC = 2
TRAIN_OPTIM = "adamw_8bit"
