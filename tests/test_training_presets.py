from __future__ import annotations

import sys
import types
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.ops import model_presets, ollama_model_presets
from src.core.training import train as train_module
from src.core.training.train import (
    PRESETS_DIR,
    get_available_presets,
    load_preset,
    resolve_preset_path,
)

ALLOWED_PRESET_TOP_LEVEL_KEYS = {"model", "training", "lora", "wandb", "logging"}
ALLOWED_TRAINING_KEYS = {
    "output_dir",
    "num_epochs",
    "max_steps",
    "batch_size",
    "gradient_accumulation_steps",
    "warmup_steps",
    "learning_rate",
    "lr_scheduler_type",
    "weight_decay",
    "neftune_noise_alpha",
    "save_steps",
    "eval_steps",
    "dataset_text_field",
    "dataset_num_proc",
    "max_seq_length",
    "packing",
    "train_on_responses_only",
}
ALLOWED_LORA_KEYS = {"r", "alpha", "dropout", "target_modules"}


def test_fast_3b_preset_is_discovered_from_canonical_etc_presets():
    preset_path = resolve_preset_path("fast-3b")

    assert PRESETS_DIR == PROJECT_ROOT / "etc" / "presets"
    assert preset_path == PROJECT_ROOT / "etc" / "presets" / "fast-3b.yaml"
    assert "fast-3b" in get_available_presets()


def test_fast_3b_preset_loads_neftune_from_training_config():
    preset = load_preset("fast-3b")

    assert preset["training"]["neftune_noise_alpha"] == 5.0


def test_all_canonical_training_presets_use_supported_override_shape():
    preset_paths = sorted(PRESETS_DIR.glob("*.yaml"))
    assert preset_paths

    for preset_path in preset_paths:
        preset = yaml.safe_load(preset_path.read_text(encoding="utf-8")) or {}
        assert set(preset) <= ALLOWED_PRESET_TOP_LEVEL_KEYS, preset_path.name
        assert any(key in preset for key in ("model", "training", "lora", "wandb")), (
            preset_path.name
        )

        training = preset.get("training")
        if training is not None:
            assert isinstance(training, dict), preset_path.name
            assert set(training) <= ALLOWED_TRAINING_KEYS, preset_path.name

        lora = preset.get("lora")
        if lora is not None:
            assert isinstance(lora, dict), preset_path.name
            assert set(lora) <= ALLOWED_LORA_KEYS, preset_path.name


def test_model_and_ollama_preset_maps_resolve_from_canonical_etc_files():
    assert model_presets.resolve_model_presets_path() == PROJECT_ROOT / "etc" / "model-presets.yaml"
    assert (
        ollama_model_presets.resolve_ollama_model_presets_path()
        == PROJECT_ROOT / "etc" / "ollama-model-presets.yaml"
    )
    assert (
        model_presets.resolve_training_preset("unsloth/Llama-3.2-3B-Instruct-bnb-4bit") == "fast-3b"
    )
    assert ollama_model_presets.resolve_ollama_model(role="judge") == "qwen2.5:7b"


def test_canonical_preset_wins_over_legacy_duplicate(monkeypatch, tmp_path):
    canonical_presets = tmp_path / "etc" / "presets"
    legacy_presets = tmp_path / "configs" / "presets"
    canonical_presets.mkdir(parents=True)
    legacy_presets.mkdir(parents=True)
    (canonical_presets / "duplicate.yaml").write_text(
        "training:\n  batch_size: 2\n", encoding="utf-8"
    )
    (legacy_presets / "duplicate.yaml").write_text("training:\n  batch_size: 1\n", encoding="utf-8")
    monkeypatch.setattr(train_module, "PRESETS_DIR", canonical_presets)
    monkeypatch.setattr(train_module, "LEGACY_PRESETS_DIR", legacy_presets)

    preset = train_module.load_preset("duplicate")

    assert train_module.resolve_preset_path("duplicate") == canonical_presets / "duplicate.yaml"
    assert preset["training"]["batch_size"] == 2


def test_legacy_only_preset_fallback_loads(monkeypatch, tmp_path):
    canonical_presets = tmp_path / "etc" / "presets"
    legacy_presets = tmp_path / "configs" / "presets"
    canonical_presets.mkdir(parents=True)
    legacy_presets.mkdir(parents=True)
    (legacy_presets / "legacy-only.yaml").write_text(
        "training:\n  batch_size: 3\n", encoding="utf-8"
    )
    monkeypatch.setattr(train_module, "PRESETS_DIR", canonical_presets)
    monkeypatch.setattr(train_module, "LEGACY_PRESETS_DIR", legacy_presets)

    preset = train_module.load_preset("legacy-only")

    assert train_module.resolve_preset_path("legacy-only") == legacy_presets / "legacy-only.yaml"
    assert preset["training"]["batch_size"] == 3


def test_available_presets_deduplicates_duplicate_names(monkeypatch, tmp_path):
    canonical_presets = tmp_path / "etc" / "presets"
    legacy_presets = tmp_path / "configs" / "presets"
    canonical_presets.mkdir(parents=True)
    legacy_presets.mkdir(parents=True)
    (canonical_presets / "duplicate.yaml").write_text("training: {}\n", encoding="utf-8")
    (legacy_presets / "duplicate.yaml").write_text("training: {}\n", encoding="utf-8")
    (legacy_presets / "legacy-only.yaml").write_text("training: {}\n", encoding="utf-8")
    monkeypatch.setattr(train_module, "PRESETS_DIR", canonical_presets)
    monkeypatch.setattr(train_module, "LEGACY_PRESETS_DIR", legacy_presets)

    available_presets = train_module.get_available_presets()

    assert available_presets.count("duplicate") == 1
    assert available_presets == ["duplicate", "legacy-only"]


def test_effective_config_merge_includes_preset_neftune(monkeypatch, tmp_path):
    canonical_presets = tmp_path / "etc" / "presets"
    legacy_presets = tmp_path / "configs" / "presets"
    canonical_presets.mkdir(parents=True)
    legacy_presets.mkdir(parents=True)
    (canonical_presets / "fast-3b.yaml").write_text(
        "training:\n  neftune_noise_alpha: 5.0\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump({"model": "test-model", "training": {}}), encoding="utf-8"
    )
    monkeypatch.setattr(train_module, "PRESETS_DIR", canonical_presets)
    monkeypatch.setattr(train_module, "LEGACY_PRESETS_DIR", legacy_presets)

    config = train_module.load_config(config_path, preset="fast-3b")

    assert config["training"]["neftune_noise_alpha"] == 5.0


def test_run_training_keeps_neftune_in_sft_config_not_trainer_kwargs(monkeypatch, tmp_path):
    captured = {}

    class FakeSFTConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            captured["sft_config_kwargs"] = kwargs

    class FakeSFTTrainer:
        def __init__(self, **kwargs):
            captured["trainer_kwargs"] = kwargs
            if "neftune_noise_alpha" in kwargs:
                raise TypeError("unexpected keyword argument 'neftune_noise_alpha'")

        def train(self):
            return types.SimpleNamespace(metrics={"train_loss": 0.1})

        def save_model(self, output_dir):
            captured["saved_model_dir"] = output_dir

    class FakeCuda:
        @staticmethod
        def is_bf16_supported():
            return False

        @staticmethod
        def device_count():
            return 0

        @staticmethod
        def is_available():
            return False

    class FakeTokenizer:
        def save_pretrained(self, output_dir):
            captured["saved_tokenizer_dir"] = output_dir

    fake_trl = types.SimpleNamespace(SFTTrainer=FakeSFTTrainer, SFTConfig=FakeSFTConfig)
    fake_torch = types.SimpleNamespace(cuda=FakeCuda())
    monkeypatch.setitem(sys.modules, "trl", fake_trl)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    train_module.run_training(
        model=object(),
        tokenizer=FakeTokenizer(),
        dataset=[{"text": "example"}],
        eval_dataset=None,
        config={
            "training": {
                "output_dir": str(tmp_path / "out"),
                "neftune_noise_alpha": 5.0,
                "num_epochs": 1,
                "batch_size": 1,
            },
            "logging": {"enable_tensorboard": False},
        },
        preset_name="fast-3b",
    )

    assert captured["sft_config_kwargs"]["neftune_noise_alpha"] == 5.0
    assert "neftune_noise_alpha" not in captured["trainer_kwargs"]
