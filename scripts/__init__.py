"""Legacy import aliases for the categorized scripts layout.

The runnable entrypoints now live under category subpackages such as
scripts.dataset, scripts.training, scripts.evaluation, scripts.export,
scripts.orchestration, and scripts.ops.

This package keeps old import paths working for code that still does things
like `from scripts import smoke_test` or `from scripts.generate_dataset
import generate_dataset`.
"""

from importlib import import_module
from types import ModuleType
import sys


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
        return getattr(self._load(), item)

    def __dir__(self):
        return dir(self._load())


_LEGACY_MODULES = {
    "audit": "scripts.ops.audit",
    "batch_export": "scripts.export.batch_export",
    "colab_notebook_generator": "scripts.ops.colab_notebook_generator",
    "compare_quality_gates": "scripts.dataset.compare_quality_gates",
    "compare_runs": "scripts.evaluation.compare_runs",
    "convert_lora_to_gguf": "scripts.export.convert_lora_to_gguf",
    "dataset_contracts": "scripts.dataset.dataset_contracts",
    "dataset_eval": "scripts.dataset.dataset_eval",
    "deploy_to_unity": "scripts.export.deploy_to_unity",
    "evaluate": "scripts.evaluation.evaluate",
    "export": "scripts.export.export",
    "export_adapter": "scripts.export.export_adapter",
    "export_resume": "scripts.export.export_resume",
    "feedback_loop": "scripts.training.feedback_loop",
    "generate_dataset": "scripts.dataset.generate_dataset",
    "generate_dataset_ollama": "scripts.dataset.generate_dataset_ollama",
    "generate_workflow_dataset": "scripts.dataset.generate_workflow_dataset",
    "iterate_feedback": "scripts.training.iterate_feedback",
    "plan_batch_execution": "scripts.orchestration.plan_batch_execution",
    "plan_execution": "scripts.orchestration.plan_execution",
    "quick_eval": "scripts.evaluation.quick_eval",
    "sanitize_dataset": "scripts.dataset.sanitize_dataset",
    "scaffold_npc": "scripts.ops.scaffold_npc",
    "smoke_test": "scripts.ops.smoke_test",
    "supabase_integration_check": "scripts.ops.supabase_integration_check",
    "tb_reader": "scripts.evaluation.tb_reader",
    "track_eval_results": "scripts.evaluation.track_eval_results",
    "train": "scripts.training.train",
    "validate_config": "scripts.ops.validate_config",
    "validate_subject_spec": "scripts.dataset.validate_subject_spec",
    "wb_report": "scripts.evaluation.wb_report",
}

__all__ = list(_LEGACY_MODULES.keys())

for legacy_name, target_module in _LEGACY_MODULES.items():
    proxy = _LazyAliasModule(legacy_name, target_module)
    sys.modules[f"{__name__}.{legacy_name}"] = proxy
    globals()[legacy_name] = proxy
