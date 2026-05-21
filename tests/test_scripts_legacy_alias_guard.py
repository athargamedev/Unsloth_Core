import importlib.util
import sys
import types
from pathlib import Path

import pytest



def load_local_scripts_module():
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "scripts" / "__init__.py"
    spec = importlib.util.spec_from_file_location("ucore_scripts_test", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_lazy_alias_proxy_ignores_dunder_attrs(monkeypatch):
    scripts_mod = load_local_scripts_module()
    sentinel = types.SimpleNamespace(answer=42)
    calls = []

    def fake_import_module(target):
        calls.append(target)
        return sentinel

    monkeypatch.setattr(scripts_mod, "import_module", fake_import_module)

    proxy = scripts_mod._LazyAliasModule("demo", "example.target")

    with pytest.raises(AttributeError):
        _ = proxy.__file__

    assert calls == []

    assert proxy.answer == 42
    assert calls == ["example.target"]
