"""
scripts/colab/render.py — Jinja2 rendering of the Colab notebook template.

The template (``template.ipynb.j2``) produces a valid ``.ipynb`` JSON string
that mirrors the cell structure of official Unsloth Colab notebooks.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import jinja2


def _json_inside(value) -> str:
    """Like ``|tojson`` but WITHOUT the outer quotes.

    Use this filter when embedding a variable *inside* an existing JSON
    string, e.g. in a ``"source"`` list value:

    .. code-block:: jinja

        "    model = {{ model_name | json_inside }},\\n",

    The ``|tojson`` filter would add its own surrounding double-quotes,
    breaking the JSON structure.
    """
    dumped = json.dumps(value, ensure_ascii=True)
    # Strip the outer quotes — what remains is properly escaped for JSON
    return dumped[1:-1]


def _find_template_path(template_path: str | None = None) -> str:
    """Locate the Jinja2 template file.

    Resolution order:
    1. Explicit *template_path* argument.
    2. Next to ``render.py`` (i.e. ``scripts/colab/template.ipynb.j2``).
    """
    if template_path is not None:
        resolved = Path(template_path)
        if not resolved.is_file():
            raise FileNotFoundError(
                f"Notebook template not found at explicit path: {template_path}"
            )
        return str(resolved)

    here = Path(__file__).resolve().parent
    default = here / "template.ipynb.j2"
    if not default.is_file():
        raise FileNotFoundError(
            f"Default notebook template not found at: {default}"
        )
    return str(default)


def _build_data_loading_code(vars: dict) -> str:
    """Build the COMPLETE Python source for the data loading cell based on data_mode."""
    preamble = (
        'from unsloth.chat_templates import get_chat_template\n'
        'from datasets import Dataset, load_dataset\n'
        'import json\n'
        '\n'
        'tokenizer = get_chat_template(\n'
        '    tokenizer,\n'
        '    chat_template = "chatml",\n'
        ')\n'
        '\n'
    )

    mode = vars.get("data_mode", "inline")

    if mode == "hf":
        url = vars.get("hf_data_files_url", "")
        body = (
            'dataset = load_dataset(\n'
            '    "json",\n'
            f'    data_files = "{url}",\n'
            '    split = "train",\n'
            ')\n'
        )
    elif mode == "drive":
        dp_path = vars.get("drive_data_path", "/content/drive/MyDrive/Unsloth/datasets/data.jsonl")
        body = (
            '# Mount Google Drive to access training datasets\n'
            'from google.colab import drive\n'
            "drive.mount('/content/drive')\n"
            '\n'
            f'dataset_path = "{dp_path}"\n'
            'print(f"Loading dataset from Drive: {dataset_path}")\n'
            'dataset = load_dataset(\n'
            '    "json",\n'
            '    data_files = dataset_path,\n'
            '    split = "train",\n'
            ')\n'
        )
    else:  # inline
        inline_data = vars.get("inline_data_jsonl", "")
        body = (
            'inline_jsonl = """' + inline_data + '"""\n'
            "lines = [ln for ln in inline_jsonl.strip().split(chr(10)) if ln.strip()]\n"
            "records = [json.loads(ln) for ln in lines]\n"
            "dataset = Dataset.from_list(records)\n"
        )

    postamble = (
        'print(f"Loaded {len(dataset)} training examples")\n'
        '\n'
        'def format_chat(example):\n'
        '    example["text"] = tokenizer.apply_chat_template(\n'
        '        example["messages"], tokenize=False, add_generation_prompt=False,\n'
        '    )\n'
        '    return example\n'
        '\n'
        'dataset = dataset.map(format_chat)\n'
        'print(f"Example text:\\n{dataset[0][\'text\'][:200]}...")\n'
    )

    return preamble + body + postamble


def _build_sft_trainer_code(vars: dict) -> str:
    """Build the COMPLETE Python source for the SFT trainer cell."""
    max_steps = vars.get("max_steps", -1)
    num_train_epochs = vars.get("num_train_epochs", 3)

    if max_steps > 0:
        max_steps_config = (
            "        max_steps = max_steps,\n"
            "        num_train_epochs = 1,\n"
        )
    else:
        max_steps_config = (
            "        num_train_epochs = num_train_epochs,\n"
        )

    learning_rate = vars.get("learning_rate", 2e-4)
    warmup_steps = vars.get("warmup_steps", 10)
    weight_decay = vars.get("weight_decay", 0.01)
    optim = vars.get("optim", "adamw_8bit")
    lr_scheduler_type = vars.get("lr_scheduler_type", "linear")
    seed = vars.get("seed", 42)

    return (
        "from trl import SFTTrainer\n"
        "from transformers import TrainingArguments\n"
        "\n"
        "# packing is disabled: train_on_responses_only (applied below) requires\n"
        "# packing=False to correctly mask instruction tokens at sequence boundaries.\n"
        "trainer = SFTTrainer(\n"
        "    model = model,\n"
        "    tokenizer = tokenizer,\n"
        "    train_dataset = dataset,\n"
        "    dataset_text_field = \"text\",\n"
        "    max_seq_length = max_seq_length,\n"
        "    dataset_num_proc = 2,\n"
        "    packing = False,\n"
        "    args = TrainingArguments(\n"
        "        output_dir = output_dir,\n"
        "        per_device_train_batch_size = per_device_train_batch_size,\n"
        "        gradient_accumulation_steps = gradient_accumulation_steps,\n"
        + max_steps_config +
        "        learning_rate = learning_rate,\n"
        "        warmup_steps = warmup_steps,\n"
        "        weight_decay = weight_decay,\n"
        "        logging_steps = 1,\n"
        "        optim = optim,\n"
        "        lr_scheduler_type = lr_scheduler_type,\n"
        "        seed = seed,\n"
        "        fp16 = not torch.cuda.is_bf16_supported(),\n"
        "        bf16 = torch.cuda.is_bf16_supported(),\n"
        '        report_to = "none",\n'
        "        remove_unused_columns = False,\n"
        "        ddp_find_unused_parameters = False if torch.cuda.device_count() > 1 else None,\n"
        "        dataloader_pin_memory = False,\n"
        "    ),\n"
        ")\n"
    )


def _build_lora_export_code(vars: dict) -> str:
    """Build Python code to save the PEFT LoRA adapter and convert to GGUF.

    Produces a small GGUF adapter file (~10-30 MB) suitable for Unity runtime
    loading via LLMUnity's SetLoraWeight -- NOT a full model merge.

    Converter strategy (in order):
    1. Check ~/.unsloth/llama.cpp/ (created by Unsloth's first GGUF export)
    2. Download just the converter script from GitHub (faster than cloning the
    whole llama.cpp repo, and the pip-installed ``gguf`` package covers
    the required imports)
    3. Fall back to local conversion instructions
    """
    npc_key = vars.get("npc_key", "npc")
    outtype = vars.get("lora_outtype", "f16")
    lines = []

    lines.append('import os, sys, json, subprocess')
    lines.append('from pathlib import Path')
    lines.append('')
    lines.append('# 1. Save the PEFT LoRA adapter (just delta weights, ~10-30 MB)')
    lines.append(f'adapter_dir = "outputs/{npc_key}"')
    lines.append('model.save_pretrained(adapter_dir)')
    lines.append('tokenizer.save_pretrained(adapter_dir)')
    lines.append('adapter_files = [f for f in os.listdir(adapter_dir) if os.path.isfile(os.path.join(adapter_dir, f))]')
    lines.append('total_mb = sum(os.path.getsize(os.path.join(adapter_dir, f)) for f in adapter_files) / (1024 * 1024)')
    lines.append('print(f"  LoRA adapter saved to {adapter_dir} ({total_mb:.1f} MB)")')
    lines.append('for f in adapter_files:')
    lines.append('    size_mb = os.path.getsize(os.path.join(adapter_dir, f)) / (1024 * 1024)')
    lines.append('    print(f"    {f}: {size_mb:.1f} MB")')
    lines.append('')
    lines.append('# 2. Read base model name from adapter config')
    lines.append('adapter_config_path = os.path.join(adapter_dir, "adapter_config.json")')
    lines.append('base_model_id = None')
    lines.append('if os.path.exists(adapter_config_path):')
    lines.append('    with open(adapter_config_path) as f:')
    lines.append('        ac = json.load(f)')
    lines.append('    base_model_id = ac.get("base_model_name_or_path", "")')
    lines.append('    print(f"  Base model: {base_model_id}")')
    lines.append('')
    lines.append('# 3. Find or download the converter')
    lines.append('converter = None')
    lines.append('#   3a. Check ~/.unsloth/llama.cpp/ (created by save_pretrained_gguf)')
    lines.append('unsloth_converter = os.path.expanduser("~/.unsloth/llama.cpp/convert_lora_to_gguf.py")')
    lines.append('if os.path.exists(unsloth_converter):')
    lines.append('    converter = unsloth_converter')
    lines.append('    print(f"  Found converter at: {converter}")')
    lines.append('')
    lines.append('if not converter:')
    lines.append('    #   3b. Download just the converter script from GitHub (fast, ~30 KB)')
    lines.append('    print("  Converter not found locally. Downloading from GitHub...")')
    lines.append('    import urllib.request')
    lines.append('    CONVERTER_URL = "https://raw.githubusercontent.com/ggml-org/llama.cpp/master/convert_lora_to_gguf.py"')
    lines.append('    try:')
    lines.append('        urllib.request.urlretrieve(CONVERTER_URL, "convert_lora_to_gguf.py")')
    lines.append('        converter = "convert_lora_to_gguf.py"')
    lines.append('        print("  Downloaded convert_lora_to_gguf.py")')
    lines.append('    except Exception as e:')
    lines.append('        print(f"  ERROR downloading converter: {e}")')
    lines.append('')
    lines.append(f'out_file = "{npc_key}-lora.{outtype}.gguf"')
    lines.append('')
    lines.append('if converter and os.path.exists(converter):')
    lines.append('    print(f"  Converting LoRA to GGUF ({outtype})...")')
    lines.append('')
    lines.append('    # Use --base-model-id to let the converter fetch clean config from HF hub')
    lines.append('    # (avoids bitsandbytes quantization keys in cached configs)')
    lines.append('    cmd = [sys.executable, converter, adapter_dir,')
    lines.append(f'           "--outtype", "{outtype}",')
    lines.append('           "--outfile", out_file]')
    lines.append('    if base_model_id:')
    lines.append('        cmd.extend(["--base-model-id", base_model_id])')
    lines.append('')
    lines.append('    result = subprocess.run(cmd, capture_output=True, text=True)')
    lines.append('    print(result.stdout)')
    lines.append('    if result.returncode != 0:')
    lines.append('        print(result.stderr)')
    lines.append('')
    lines.append('    if os.path.exists(out_file):')
    lines.append('        size_mb = os.path.getsize(out_file) / (1024 * 1024)')
    lines.append('        print(f"\\n  SUCCESS: LoRA GGUF adapter ready!")')
    lines.append('        print(f"  File: {out_file}")')
    lines.append('        print(f"  Size: {size_mb:.1f} MB")')
    lines.append('        print(f"  Place in Unity: Assets/StreamingAssets/")')
    lines.append('        print(f"  Load via SetLoraWeight on the LLM GameObject")')
    lines.append('    else:')
    lines.append('        print(f"\\n  Conversion may have failed. Check output above.")')
    lines.append('else:')
    lines.append('    print(f"\\n  Converter unavailable. LoRA adapter stays at {adapter_dir}/")')
    lines.append('    print("  Convert it locally after transferring adapter from Colab:")')
    lines.append('    print(f"    # 1. Zip the adapter folder from Colab\'s Files sidebar")')
    lines.append('    print(f"    # 2. Download outputs/{npc_key}/adapter_model.safetensors + adapter_config.json")')
    lines.append('    print(f"    # 3. On this machine run:")')
    lines.append('    print(f"    python scripts/export_adapter.py outputs/{npc_key} --outtype {outtype}")')

    return "\n".join(lines)


def _build_gguf_save_code(vars: dict) -> str:
    """Build the Python source for the LoRA GGUF save/export cell.

    Copies the small LoRA GGUF file to Google Drive (drive mode) or
    offers direct download (inline/hf mode). The file is ~10-30 MB.
    """
    mode = vars.get("data_mode", "inline")
    npc_key = vars.get("npc_key", "npc")
    outtype = vars.get("lora_outtype", "f16")
    lora_gguf_filename = f"{npc_key}-lora.{outtype}.gguf"
    adapter_dir = f"outputs/{npc_key}"
    lines = []

    if mode == "drive":
        drive_dir = vars.get("drive_gguf_dir", "/content/drive/MyDrive/Unsloth/gguf/")
        lines.append('import os, shutil')
        lines.append('')
        lines.append(f'lora_gguf = "{lora_gguf_filename}"')
        lines.append('if os.path.exists(lora_gguf):')
        lines.append(f'    drive_gguf_dir = "{drive_dir}"')
        lines.append('    os.makedirs(drive_gguf_dir, exist_ok=True)')
        lines.append('    dst = os.path.join(drive_gguf_dir, lora_gguf)')
        lines.append('    shutil.copy2(lora_gguf, dst)')
        lines.append('    size_mb = os.path.getsize(dst) / (1024 * 1024)')
        lines.append('    print(f"LoRA GGUF saved to Drive: {dst}")')
        lines.append('    print(f"Size: {size_mb:.1f} MB")')
        lines.append('    print("")')
        lines.append('    print("Next: Copy this file to your Unity project:")')
        lines.append(f'    print("  Assets/StreamingAssets/{lora_gguf_filename}")')
        lines.append('    print("Then load via SetLoraWeight on the LLM GameObject")')
        lines.append('else:')
        lines.append(f'    print(f"LoRA GGUF not found: {lora_gguf_filename}")')
        lines.append(f'    print(f"Adapter PEFT files saved at outputs/{npc_key}/ -- convert locally:")')
        lines.append(f'    print(f"  python scripts/export_adapter.py outputs/{npc_key} --outtype {outtype}")')
    else:
        # inline or hf mode -- offer download
        lines.append('import os')
        lines.append('')
        lines.append(f'lora_gguf = "{lora_gguf_filename}"')
        lines.append('if os.path.exists(lora_gguf):')
        lines.append('    size_mb = os.path.getsize(lora_gguf) / (1024 * 1024)')
        lines.append(f'    print(f"LoRA GGUF ready: {{lora_gguf}} ({{size_mb:.1f}} MB)")')
        lines.append('    print("Downloading...")')
        lines.append('    from google.colab import files')
        lines.append('    files.download(lora_gguf)')
        lines.append('    print("")')
        lines.append('    print("Next: Copy to Unity Assets/StreamingAssets/")')
        lines.append('    print("  Then load via SetLoraWeight on the LLM GameObject")')
        lines.append('else:')
        lines.append(f'    print(f"LoRA GGUF not found: {{lora_gguf}}")')
        lines.append(f'    print(f"Adapter PEFT files saved at outputs/{npc_key}/ -- convert locally:")')
        lines.append(f'    print(f"  python scripts/export_adapter.py outputs/{npc_key} --outtype {outtype}")')

    return "\n".join(lines)


def render_notebook(
    template_vars: dict,
    template_path: str | None = None,
) -> str:
    """Render the Jinja2 notebook template into a ``.ipynb`` JSON string.

    Parameters
    ----------
    template_vars : dict
        Variables to inject into the template.
    template_path : str | None
        Explicit path to a ``.ipynb.j2`` template file.

    Returns
    -------
    str
        The rendered notebook as a valid JSON string.

    Raises
    ------
    FileNotFoundError
        Template file not found.
    ValueError
        Rendered output is not valid JSON.
    """
    template_file = _find_template_path(template_path)

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(os.path.dirname(template_file)),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    # Register custom filters
    env.filters["json_inside"] = _json_inside

    template = env.get_template(os.path.basename(template_file))

    # ── Pre-compute conditional cell code ──────────────────────────────────
    # Build these in Python so the Jinja2 template has no conditionals
    build_vars = dict(template_vars)
    build_vars["data_loading_code"] = _build_data_loading_code(template_vars)
    build_vars["sft_trainer_code"] = _build_sft_trainer_code(template_vars)
    build_vars["lora_export_code"] = _build_lora_export_code(template_vars)
    build_vars["gguf_save_code"] = _build_gguf_save_code(template_vars)

    rendered = template.render(**build_vars)

    # ── Validate that the output is valid JSON ─────────────────────────────
    try:
        json.loads(rendered)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Rendered notebook is not valid JSON. Template issue at: {exc}"
        )

    return rendered
