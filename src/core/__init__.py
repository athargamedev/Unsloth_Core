"""Legacy import aliases for the categorized scripts layout.

The runnable entrypoints now live under category subpackages such as
src.core.dataset, src.core.training, src.core.evaluation, src.core.export,
src.core.orchestration, and src.core.ops.

This package keeps old import paths working for code that still does things
like `from src.core import smoke_test` or `from src.core.generate_dataset
import generate_dataset`.
"""

import sys
from importlib import import_module
from types import ModuleType


class _LazyAliasModule(ModuleType):
    def __init__(self, legacy_name: str, target_module: str):
        super().__init__(f"{__name__}.{legacy_name}")
        super().__setattr__("_legacy_name", legacy_name)
        super().__setattr__("_target_module", target_module)
        super().__setattr__("_loaded", None)

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        if name not in {
            "__name__",
            "__loader__",
            "__package__",
            "__spec__",
            "__path__",
            "__file__",
            "__cached__",
            "__builtins__",
            "_legacy_name",
            "_target_module",
            "_loaded",
        }:
            loaded = self.__dict__.get("_loaded")
            if loaded is not None:
                setattr(loaded, name, value)

    def _load(self) -> ModuleType:
        loaded = self.__dict__.get("_loaded")
        if loaded is not None:
            return loaded

        target = self.__dict__["_target_module"]
        module = import_module(target)

        blocked = {
            "__name__",
            "__loader__",
            "__package__",
            "__spec__",
            "__path__",
            "__file__",
            "__cached__",
            "__builtins__",
            "_legacy_name",
            "_target_module",
            "_loaded",
        }
        for key, value in list(self.__dict__.items()):
            if key not in blocked:
                setattr(module, key, value)

        super().__setattr__("_loaded", module)
        sys.modules[self.__name__] = module
        globals()[self.__dict__["_legacy_name"]] = module
        return module

    def __getattr__(self, item):
        if item.startswith("__"):
            raise AttributeError(item)
        return getattr(self._load(), item)

    def __dir__(self):
        return dir(self._load())


_LEGACY_MODULES = {
    "audit": "src.core.ops.audit",
    "compare_local_models": "src.core.ops.compare_local_models",
    "compare_runs": "src.core.evaluation.compare_runs",
    "convert_lora_to_gguf": "src.core.export.convert_lora_to_gguf",
    "dataset_contracts": "src.core.dataset.dataset_contracts",
    "dataset_eval": "src.core.dataset.dataset_eval",
    "evaluate": "src.core.evaluation.evaluate",
    "export": "src.core.export.export",
    "export_adapter": "src.core.export.export_adapter",
    "feedback_loop": "src.core.training.feedback_loop",
    "generate_dataset": "src.core.dataset.generate_dataset",
    "generate_dataset_ollama": "src.core.dataset.generate_dataset",
    "generate_workflow_dataset": "src.core.dataset.generate_workflow_dataset",
    "plan_execution": "src.core.orchestration.plan_execution",
    "quick_eval": "src.core.evaluation.quick_eval",
    "sanitize_dataset": "src.core.dataset.sanitize_dataset",
    "smoke_test": "src.core.ops.smoke_test",
    "track_eval_results": "src.core.evaluation.track_eval_results",
    "train": "src.core.training.train",
    "validate_subject_spec": "src.core.dataset.validate_subject_spec",
}

__all__ = list(_LEGACY_MODULES.keys())

for legacy_name, target_module in _LEGACY_MODULES.items():
    proxy = _LazyAliasModule(legacy_name, target_module)
    sys.modules[f"{__name__}.{legacy_name}"] = proxy
    globals()[legacy_name] = proxy
