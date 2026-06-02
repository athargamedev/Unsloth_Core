"""Tests for the Confident AI REST API client.

Tests the ``ConfidentAPIClient`` class from ``scripts/ops/confident_api.py``
using mocked HTTP calls (no real network requests).
"""

import json
import sys
import urllib.error
import urllib.request
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(data: dict, status: int = 200) -> MagicMock:
    """Build a mock ``urllib.request.urlopen`` context-manager response.

    The returned mock supports ``with urlopen(...) as resp:`` and
    ``resp.read()`` patterns used by ``ConfidentAPIClient._request``.
    """
    resp = MagicMock()
    resp.read.return_value = json.dumps(data).encode("utf-8")
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    resp.status = status
    return resp


# ===================================================================
# Public API — Key Resolution
# ===================================================================


class TestKeyResolution:
    """Api-key resolution: argument, env var, and missing-key error."""

    def test_accepts_api_key_argument(self):
        """Key passed as constructor argument is used directly."""
        from scripts.ops.confident_api import ConfidentAPIClient

        client = ConfidentAPIClient(api_key="test-key-123")
        assert client._api_key == "test-key-123"

    def test_reads_key_from_env_var(self, monkeypatch):
        """Key from ``CONFIDENT_API_KEY`` env var when argument is omitted."""
        from scripts.ops.confident_api import ConfidentAPIClient

        monkeypatch.setenv("CONFIDENT_API_KEY", "env-key-value")
        client = ConfidentAPIClient()
        assert client._api_key == "env-key-value"

    def test_raises_error_when_key_missing(self, monkeypatch):
        """No key anywhere raises ``EnvironmentError``."""
        from scripts.ops.confident_api import ConfidentAPIClient

        monkeypatch.delenv("CONFIDENT_API_KEY", raising=False)
        with patch("src.core.ops.env_loader.load_env_local", return_value=False):
            with pytest.raises(EnvironmentError, match="CONFIDENT_API_KEY"):
                ConfidentAPIClient()


# ===================================================================
# Public API — Evaluation Methods
# ===================================================================


class TestEvaluate:
    """``evaluate()`` — POST /v1/evaluate with ``llmTestCases``."""

    def test_sends_correct_request(self):
        """Happy path: POST with correct body, returns testRunId."""
        from scripts.ops.confident_api import ConfidentAPIClient

        client = ConfidentAPIClient(api_key="test-key")
        test_cases = [{"input": "Hello", "actualOutput": "Hi"}]
        metrics = {"name": "test", "include": ["faithfulness"]}
        mock = _mock_response({"success": True, "data": {"testRunId": "run-1"}})

        with patch("urllib.request.urlopen", return_value=mock) as mock_urlopen:
            result = client.evaluate(test_cases, metrics, identifier="my-eval")

        assert result["success"] is True
        assert result["data"]["testRunId"] == "run-1"

        req = mock_urlopen.call_args[0][0]
        assert req.method == "POST"
        assert req.full_url.endswith("/evaluate")

        body = json.loads(req.data)
        assert body["metricCollection"] == "test"
        assert body["llmTestCases"] == test_cases
        assert body["identifier"] == "my-eval"
        assert body["hyperparameters"] == {}

    def test_sends_custom_hyperparameters(self):
        """When hyperparameters dict is provided, it is populated in the body."""
        from scripts.ops.confident_api import ConfidentAPIClient

        client = ConfidentAPIClient(api_key="test-key")
        test_cases = [{"input": "Hello", "actualOutput": "Hi"}]
        metrics = {"name": "test", "include": ["faithfulness"]}
        mock = _mock_response({"success": True, "data": {"testRunId": "run-1"}})
        hparams = {"temperature": "0.3", "judge_model": "qwen2.5:7b"}

        with patch("urllib.request.urlopen", return_value=mock) as mock_urlopen:
            client.evaluate(test_cases, metrics, identifier="my-eval", hyperparameters=hparams)

        body = json.loads(mock_urlopen.call_args[0][0].data)
        assert body["hyperparameters"] == hparams

    def test_without_identifier_omits_field(self):
        """When identifier is None it must not appear in the body."""
        from scripts.ops.confident_api import ConfidentAPIClient

        client = ConfidentAPIClient(api_key="test-key")
        mock = _mock_response({"success": True})

        with patch("urllib.request.urlopen", return_value=mock) as mock_urlopen:
            client.evaluate([{"input": "Hi", "actualOutput": "Hello"}],
                            {"name": "t", "include": []})

        body = json.loads(mock_urlopen.call_args[0][0].data)
        assert "identifier" not in body


class TestEvaluateConversational:
    """``evaluate_conversational()`` — POST /v1/evaluate with ``conversationalTestCases``."""

    def test_sends_correct_request(self):
        """Happy path with conversational test cases."""
        from scripts.ops.confident_api import ConfidentAPIClient

        client = ConfidentAPIClient(api_key="test-key")
        test_cases = [{"messages": [{"role": "user", "content": "Hi"}]}]
        metrics = {"name": "conv-test", "include": ["coherence"]}
        mock = _mock_response({"success": True, "data": {"testRunId": "conv-run-1"}})

        with patch("urllib.request.urlopen", return_value=mock) as mock_urlopen:
            result = client.evaluate_conversational(
                test_cases, metrics, identifier="conv-eval"
            )

        assert result["success"] is True

        req = mock_urlopen.call_args[0][0]
        assert req.method == "POST"
        assert req.full_url.endswith("/evaluate")

        body = json.loads(req.data)
        assert body["conversationalTestCases"] == test_cases
        assert body["metricCollection"] == "conv-test"
        assert body["identifier"] == "conv-eval"
        assert body["hyperparameters"] == {}

    def test_sends_custom_hyperparameters(self):
        """Conversational eval propagates custom hyperparameters dict in the body."""
        from scripts.ops.confident_api import ConfidentAPIClient

        client = ConfidentAPIClient(api_key="test-key")
        test_cases = [{"messages": [{"role": "user", "content": "Hi"}]}]
        metrics = {"name": "conv-test", "include": ["coherence"]}
        mock = _mock_response({"success": True, "data": {"testRunId": "conv-run-1"}})
        hparams = {"temperature": "0.3", "judge_model": "qwen2.5:7b"}

        with patch("urllib.request.urlopen", return_value=mock) as mock_urlopen:
            client.evaluate_conversational(test_cases, metrics, identifier="conv-eval", hyperparameters=hparams)

        body = json.loads(mock_urlopen.call_args[0][0].data)
        assert body["hyperparameters"] == hparams

    def test_without_identifier_omits_field(self):
        """Conversational eval without identifier field."""
        from scripts.ops.confident_api import ConfidentAPIClient

        client = ConfidentAPIClient(api_key="test-key")
        mock = _mock_response({"success": True})

        with patch("urllib.request.urlopen", return_value=mock) as mock_urlopen:
            client.evaluate_conversational([], {"name": "t", "include": []})

        body = json.loads(mock_urlopen.call_args[0][0].data)
        assert "identifier" not in body


# ===================================================================
# Public API — Dataset Methods
# ===================================================================


class TestPushDataset:
    """``push_dataset()`` — POST /v1/datasets/:alias."""

    def test_sends_correct_request(self):
        """Happy path with version and finalized=True."""
        from scripts.ops.confident_api import ConfidentAPIClient

        client = ConfidentAPIClient(api_key="test-key")
        goldens = [{"input": "Q", "actualOutput": "A"}]
        mock = _mock_response({"success": True})

        with patch("urllib.request.urlopen", return_value=mock) as mock_urlopen:
            result = client.push_dataset("my-dataset", goldens,
                                         version="1.0.0", finalized=True)

        assert result["success"] is True

        req = mock_urlopen.call_args[0][0]
        assert req.method == "POST"
        assert "/datasets/my-dataset" in req.full_url

        body = json.loads(req.data)
        assert body["goldens"] == goldens
        assert body["finalized"] is True
        assert body["version"] == "1.0.0"

    def test_without_version_omits_field(self):
        """Version key absent from body when not provided."""
        from scripts.ops.confident_api import ConfidentAPIClient

        client = ConfidentAPIClient(api_key="test-key")
        mock = _mock_response({"success": True})

        with patch("urllib.request.urlopen", return_value=mock) as mock_urlopen:
            client.push_dataset("my-dataset", [], finalized=False)

        body = json.loads(mock_urlopen.call_args[0][0].data)
        assert body["finalized"] is False
        assert "version" not in body

    def test_sends_conversational_goldens_without_single_turn_goldens(self):
        """Multi-turn dataset push uses conversationalGoldens, not goldens."""
        from scripts.ops.confident_api import ConfidentAPIClient

        client = ConfidentAPIClient(api_key="test-key")
        conversational = [{"scenario": "remember user facts"}]
        mock = _mock_response({"success": True, "link": "https://app.confident-ai.com/datasets/x"})

        with patch("urllib.request.urlopen", return_value=mock) as mock_urlopen:
            result = client.push_dataset(
                "my-conversation-dataset",
                conversational_goldens=conversational,
                finalized=False,
            )

        assert result["success"] is True
        body = json.loads(mock_urlopen.call_args[0][0].data)
        assert body["conversationalGoldens"] == conversational
        assert "goldens" not in body
        assert body["finalized"] is False

    def test_rejects_mixed_single_and_conversational_goldens(self):
        """Confident datasets should not mix single-turn and multi-turn payloads."""
        from scripts.ops.confident_api import ConfidentAPIClient

        client = ConfidentAPIClient(api_key="test-key")
        with pytest.raises(ValueError, match="exactly one"):
            client.push_dataset(
                "mixed",
                goldens=[{"input": "Q"}],
                conversational_goldens=[{"scenario": "S"}],
            )


class TestPullDataset:
    """``pull_dataset()`` — GET /v1/datasets/:alias."""

    def test_returns_goldens(self):
        """Returns ``goldens`` list from response."""
        from scripts.ops.confident_api import ConfidentAPIClient

        client = ConfidentAPIClient(api_key="test-key")
        mock = _mock_response({"goldens": [{"input": "Q", "actualOutput": "A"}]})

        with patch("urllib.request.urlopen", return_value=mock) as mock_urlopen:
            result = client.pull_dataset("my-dataset")

        assert result == [{"input": "Q", "actualOutput": "A"}]

        req = mock_urlopen.call_args[0][0]
        assert req.method == "GET"
        assert "/datasets/my-dataset" in req.full_url

    def test_falls_back_to_data_key(self):
        """Uses ``data`` key when ``goldens`` is absent."""
        from scripts.ops.confident_api import ConfidentAPIClient

        client = ConfidentAPIClient(api_key="test-key")
        mock = _mock_response({"data": [{"input": "fallback"}]})

        with patch("urllib.request.urlopen", return_value=mock):
            result = client.pull_dataset("my-dataset")

        assert result == [{"input": "fallback"}]

    def test_returns_raw_dict_when_no_expected_keys(self):
        """Returns the raw response dict when neither ``goldens`` nor ``data`` is present (type mismatch vs return annotation)."""
        from scripts.ops.confident_api import ConfidentAPIClient

        client = ConfidentAPIClient(api_key="test-key")
        mock = _mock_response({"unexpected": "structure"})

        with patch("urllib.request.urlopen", return_value=mock):
            result = client.pull_dataset("my-dataset")

        assert result == {"unexpected": "structure"}


class TestListDatasets:
    """``list_datasets()`` — GET /v1/datasets."""

    def test_returns_list(self):
        """Returns ``datasets`` list from response."""
        from scripts.ops.confident_api import ConfidentAPIClient

        client = ConfidentAPIClient(api_key="test-key")
        mock = _mock_response({"datasets": [{"alias": "ds-1"}, {"alias": "ds-2"}]})

        with patch("urllib.request.urlopen", return_value=mock) as mock_urlopen:
            result = client.list_datasets()

        assert len(result) == 2
        assert result[0]["alias"] == "ds-1"

        req = mock_urlopen.call_args[0][0]
        assert req.method == "GET"
        assert req.full_url.endswith("/datasets")

    def test_falls_back_to_data_key(self):
        """Uses ``data`` key when ``datasets`` is absent."""
        from scripts.ops.confident_api import ConfidentAPIClient

        client = ConfidentAPIClient(api_key="test-key")
        mock = _mock_response({"data": [{"alias": "fallback-ds"}]})

        with patch("urllib.request.urlopen", return_value=mock):
            result = client.list_datasets()

        assert result == [{"alias": "fallback-ds"}]


class TestDeleteDataset:
    """``delete_dataset()`` — DELETE /v1/datasets/:alias."""

    def test_returns_true_on_success(self):
        """Returns True regardless of response content."""
        from scripts.ops.confident_api import ConfidentAPIClient

        client = ConfidentAPIClient(api_key="test-key")
        mock = _mock_response({"success": True})

        with patch("urllib.request.urlopen", return_value=mock) as mock_urlopen:
            result = client.delete_dataset("my-dataset")

        assert result is True

        req = mock_urlopen.call_args[0][0]
        assert req.method == "DELETE"
        assert "/datasets/my-dataset" in req.full_url


class TestCreateDatasetVersion:
    """``create_dataset_version()`` — POST /v1/datasets/:alias/versions."""

    def test_sends_correct_request(self):
        """POST with goldens in body, returns response."""
        from scripts.ops.confident_api import ConfidentAPIClient

        client = ConfidentAPIClient(api_key="test-key")
        goldens = [{"input": "Q", "actualOutput": "A"}]
        mock = _mock_response({"success": True, "version": "2.0.0"})

        with patch("urllib.request.urlopen", return_value=mock) as mock_urlopen:
            result = client.create_dataset_version("my-dataset", goldens)

        assert result["success"] is True
        assert result["version"] == "2.0.0"

        req = mock_urlopen.call_args[0][0]
        assert req.method == "POST"
        assert "/datasets/my-dataset/versions" in req.full_url

        body = json.loads(req.data)
        assert body["goldens"] == goldens


class TestListDatasetVersions:
    """``list_dataset_versions()`` — GET /v1/datasets/:alias/versions."""

    def test_returns_versions(self):
        """Returns ``versions`` list from response."""
        from scripts.ops.confident_api import ConfidentAPIClient

        client = ConfidentAPIClient(api_key="test-key")
        mock = _mock_response({"versions": [{"version": "1.0.0"}]})

        with patch("urllib.request.urlopen", return_value=mock) as mock_urlopen:
            result = client.list_dataset_versions("my-dataset")

        assert result == [{"version": "1.0.0"}]

        req = mock_urlopen.call_args[0][0]
        assert req.method == "GET"
        assert "/datasets/my-dataset/versions" in req.full_url


# ===================================================================
# Public API — Test Run Methods
# ===================================================================


class TestGetTestRun:
    """``get_test_run()`` — GET /v1/test-runs/:id."""

    def test_returns_test_run_details(self):
        """Returns the full test-run response dict."""
        from scripts.ops.confident_api import ConfidentAPIClient

        client = ConfidentAPIClient(api_key="test-key")
        mock = _mock_response({"testRunId": "run-1", "status": "completed"})

        with patch("urllib.request.urlopen", return_value=mock) as mock_urlopen:
            result = client.get_test_run("run-1")

        assert result["testRunId"] == "run-1"
        assert result["status"] == "completed"

        req = mock_urlopen.call_args[0][0]
        assert req.method == "GET"
        assert "/test-runs/run-1" in req.full_url


class TestListTestRuns:
    """``list_test_runs()`` — GET /v1/test-runs."""

    def test_returns_data_key(self):
        """Returns ``data`` list from response."""
        from scripts.ops.confident_api import ConfidentAPIClient

        client = ConfidentAPIClient(api_key="test-key")
        mock = _mock_response({"data": [{"testRunId": "r1"}, {"testRunId": "r2"}]})

        with patch("urllib.request.urlopen", return_value=mock) as mock_urlopen:
            result = client.list_test_runs()

        assert len(result) == 2
        assert result[0]["testRunId"] == "r1"

        req = mock_urlopen.call_args[0][0]
        assert req.method == "GET"
        assert req.full_url.endswith("/test-runs")

    def test_falls_back_to_testRuns_key(self):
        """Uses ``testRuns`` key when ``data`` is absent."""
        from scripts.ops.confident_api import ConfidentAPIClient

        client = ConfidentAPIClient(api_key="test-key")
        mock = _mock_response({"testRuns": [{"testRunId": "fallback-run"}]})

        with patch("urllib.request.urlopen", return_value=mock):
            result = client.list_test_runs()

        assert result == [{"testRunId": "fallback-run"}]


class TestListTestRunsPaginated:
    """``list_test_runs_paginated()`` — GET /v1/test-runs?page=&pageSize=."""

    def test_sends_pagination_params(self):
        """Passes page and page_size as query parameters."""
        from scripts.ops.confident_api import ConfidentAPIClient

        client = ConfidentAPIClient(api_key="test-key")
        mock = _mock_response({"items": [{"testRunId": "r1"}], "total": 1})

        with patch("urllib.request.urlopen", return_value=mock) as mock_urlopen:
            result = client.list_test_runs_paginated(page=2, page_size=10)

        assert result["items"] == [{"testRunId": "r1"}]
        assert result["total"] == 1

        req = mock_urlopen.call_args[0][0]
        assert req.method == "GET"
        assert "page=2" in req.full_url
        assert "pageSize=10" in req.full_url

    def test_defaults_page_and_page_size(self):
        """Default page=1, page_size=20."""
        from scripts.ops.confident_api import ConfidentAPIClient

        client = ConfidentAPIClient(api_key="test-key")
        mock = _mock_response({"items": [], "total": 0})

        with patch("urllib.request.urlopen", return_value=mock) as mock_urlopen:
            client.list_test_runs_paginated()

        req = mock_urlopen.call_args[0][0]
        assert "page=1" in req.full_url
        assert "pageSize=20" in req.full_url


# ===================================================================
# Error Handling
# ===================================================================


class TestRaiseForStatus:
    """``_raise_for_status()`` maps HTTP status codes to exceptions."""

    def test_400_raises_value_error(self):
        from scripts.ops.confident_api import ConfidentAPIClient
        with pytest.raises(ValueError, match="Bad request"):
            ConfidentAPIClient._raise_for_status(400, '{"error":"bad"}', "/evaluate")

    def test_401_raises_permission_error(self):
        from scripts.ops.confident_api import ConfidentAPIClient
        with pytest.raises(PermissionError, match="API key invalid"):
            ConfidentAPIClient._raise_for_status(401, "unauthorized", "/evaluate")

    def test_403_raises_permission_error(self):
        from scripts.ops.confident_api import ConfidentAPIClient
        with pytest.raises(PermissionError, match="Access forbidden"):
            ConfidentAPIClient._raise_for_status(403, "forbidden", "/evaluate")

    def test_404_raises_file_not_found_error(self):
        from scripts.ops.confident_api import ConfidentAPIClient
        with pytest.raises(FileNotFoundError, match="Resource not found"):
            ConfidentAPIClient._raise_for_status(404, "not found",
                                                 "/datasets/unknown")

    def test_409_raises_runtime_error(self):
        from scripts.ops.confident_api import ConfidentAPIClient
        with pytest.raises(RuntimeError, match="Conflict"):
            ConfidentAPIClient._raise_for_status(409, '{"error":"conflict"}',
                                                 "/datasets/ds")

    def test_422_raises_value_error(self):
        from scripts.ops.confident_api import ConfidentAPIClient
        with pytest.raises(ValueError, match="Unprocessable"):
            ConfidentAPIClient._raise_for_status(422, "bad data", "/evaluate")

    def test_500_raises_runtime_error(self):
        from scripts.ops.confident_api import ConfidentAPIClient
        with pytest.raises(RuntimeError, match="Server error"):
            ConfidentAPIClient._raise_for_status(500, "internal error",
                                                 "/evaluate")

    def test_unknown_status_raises_runtime_error(self):
        from scripts.ops.confident_api import ConfidentAPIClient
        with pytest.raises(RuntimeError, match="HTTP 418"):
            ConfidentAPIClient._raise_for_status(418, "teapot", "/evaluate")


class TestRequestNetworkErrors:
    """``_request()`` wraps ``urllib`` errors into Python builtins."""

    def test_url_error_raises_runtime_error(self):
        """Connection errors and timeouts (``URLError``) become ``RuntimeError``."""
        from scripts.ops.confident_api import ConfidentAPIClient

        client = ConfidentAPIClient(api_key="test-key")
        mock_urlopen = MagicMock()
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        with patch("urllib.request.urlopen", mock_urlopen):
            with pytest.raises(RuntimeError, match="Network error"):
                client.evaluate([{"input": "Hi", "actualOutput": "Hello"}],
                                {"name": "t", "include": []})

    def test_http_error_through_request_raises_mapped_exception(self):
        """``HTTPError`` in ``_request`` triggers the ``_raise_for_status`` path."""
        from scripts.ops.confident_api import ConfidentAPIClient

        client = ConfidentAPIClient(api_key="test-key")
        headers = {}
        fp = BytesIO(b'{"error":"not found"}')
        http_error = urllib.error.HTTPError("/test-runs/nonexistent", 404,
                                            "Not Found", headers, fp)

        with patch("urllib.request.urlopen", side_effect=http_error):
            with pytest.raises(FileNotFoundError, match="Resource not found"):
                client.get_test_run("nonexistent")

    def test_invalid_json_response_raises_json_decode_error(self):
        """Non-JSON response raises ``json.JSONDecodeError``."""
        from scripts.ops.confident_api import ConfidentAPIClient

        client = ConfidentAPIClient(api_key="test-key")
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"not valid json"
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None

        with patch("urllib.request.urlopen", return_value=mock_resp):
            with pytest.raises(json.JSONDecodeError):
                client.evaluate([{"input": "Hi", "actualOutput": "Hello"}],
                                {"name": "t", "include": []})


# ===================================================================
# Pipeline Manifest Integration
# ===================================================================


class TestPipelineManifestConfidentUrl:
    """``record_pipeline_stage()`` metadata can hold ``confident_url``."""

    def test_accepts_confident_url_metadata(self, monkeypatch, tmp_path):
        """``confident_url`` survives the record → save → load round-trip."""
        from scripts.ops.pipeline_manifest import record_pipeline_stage

        manifest_path = tmp_path / ".pipeline" / "run_manifest.json"
        monkeypatch.setenv("NPC_KEY", "test_npc")
        monkeypatch.setenv("TECHNIQUE", "template")
        monkeypatch.setenv("UCORE_MANIFEST_PATH", str(manifest_path))

        record_pipeline_stage(
            "evaluate",
            "completed",
            metadata={"confident_url": "https://app.confident-ai.com/run/abc123"},
        )

        saved = json.loads(manifest_path.read_text())
        stage = saved["stages"][0]
        assert stage["metadata"]["confident_url"] == \
            "https://app.confident-ai.com/run/abc123"

    def test_metadata_without_confident_url(self, monkeypatch, tmp_path):
        """Other metadata keys are preserved; ``confident_url`` is optional."""
        from scripts.ops.pipeline_manifest import record_pipeline_stage

        manifest_path = tmp_path / ".pipeline" / "run_manifest.json"
        monkeypatch.setenv("NPC_KEY", "test_npc")
        monkeypatch.setenv("TECHNIQUE", "template")
        monkeypatch.setenv("UCORE_MANIFEST_PATH", str(manifest_path))

        record_pipeline_stage(
            "generate",
            "completed",
            metadata={"num_examples": 72},
        )

        saved = json.loads(manifest_path.read_text())
        stage = saved["stages"][0]
        assert "confident_url" not in stage["metadata"]
        assert stage["metadata"]["num_examples"] == 72
