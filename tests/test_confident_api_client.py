"""Tests for the standalone Confident AI REST API client.

Tests the ConfidentAPIClient without making actual HTTP calls.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(PROJECT_ROOT))

from src.core.ops.confident_api import (
    ConfidentAPIClient,
    _metric_collection_name,
)

# ---------------------------------------------------------------------------
# _metric_collection_name
# ---------------------------------------------------------------------------


class TestMetricCollectionName:
    def test_from_string_returns_string_unchanged(self):
        assert _metric_collection_name("npc-dataset-quality") == "npc-dataset-quality"

    def test_from_dict_extracts_name_key(self):
        assert (
            _metric_collection_name({"name": "npc-model-quality", "metrics": ["faithfulness"]})
            == "npc-model-quality"
        )

    def test_from_bad_dict_raises_value_error(self):
        with pytest.raises(ValueError, match="metric_collection must be a name string"):
            _metric_collection_name({"not_name": "broken"})


# ---------------------------------------------------------------------------
# ConfidentAPIClient — key resolution
# ---------------------------------------------------------------------------


class TestConfidentAPIClientInit:
    def test_init_with_explicit_key(self):
        client = ConfidentAPIClient(api_key="test-key-123")
        assert client._api_key == "test-key-123"

    def test_init_with_no_key_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(EnvironmentError, match="CONFIDENT_API_KEY"):
                ConfidentAPIClient()

    def test_init_reads_from_env(self):
        with patch.dict(os.environ, {"CONFIDENT_API_KEY": "env-key-456"}, clear=True):
            client = ConfidentAPIClient()
            assert client._api_key == "env-key-456"

    def test_init_explicit_key_overrides_env(self):
        with patch.dict(os.environ, {"CONFIDENT_API_KEY": "env-key"}, clear=True):
            client = ConfidentAPIClient(api_key="explicit-key")
            assert client._api_key == "explicit-key"


# ---------------------------------------------------------------------------
# ConfidentAPIClient — evaluate()
# ---------------------------------------------------------------------------


class TestConfidentAPIClientEvaluate:
    @pytest.fixture
    def client(self):
        with patch.dict(os.environ, {"CONFIDENT_API_KEY": "test-key"}, clear=True):
            return ConfidentAPIClient()

    def test_evaluate_builds_correct_payload(self, client):
        test_cases = [{"input": "Hello", "actualOutput": "Hi"}]
        mc = {"name": "npc-dataset-quality"}

        with patch.object(client, "_request", return_value={"success": True}) as mock_request:
            result = client.evaluate(test_cases, mc, identifier="test-run-1")

        mock_request.assert_called_once_with(
            "POST",
            "/evaluate",
            {
                "metricCollection": "npc-dataset-quality",
                "llmTestCases": test_cases,
                "identifier": "test-run-1",
                "hyperparameters": {},
            },
        )

    def test_evaluate_without_identifier(self, client):
        test_cases = [{"input": "Q", "actualOutput": "A"}]
        mc = "npc-model-quality"

        with patch.object(client, "_request", return_value={"success": True}) as mock_request:
            client.evaluate(test_cases, mc)

        expected_body = {
            "metricCollection": "npc-model-quality",
            "llmTestCases": test_cases,
            "hyperparameters": {},
        }
        mock_request.assert_called_once_with("POST", "/evaluate", expected_body)

    def test_evaluate_passes_hyperparameters(self, client):
        test_cases = [{"input": "Q", "actualOutput": "A"}]
        mc = "npc-dataset-quality"
        hp = {"model": "qwen2.5:7b", "temperature": 0.0}

        with patch.object(client, "_request", return_value={"success": True}) as mock_request:
            client.evaluate(test_cases, mc, hyperparameters=hp)

        expected_body = {
            "metricCollection": "npc-dataset-quality",
            "llmTestCases": test_cases,
            "hyperparameters": hp,
        }
        mock_request.assert_called_once_with("POST", "/evaluate", expected_body)


# ---------------------------------------------------------------------------
# ConfidentAPIClient — evaluate_conversational()
# ---------------------------------------------------------------------------


class TestConfidentAPIClientEvaluateConversational:
    @pytest.fixture
    def client(self):
        with patch.dict(os.environ, {"CONFIDENT_API_KEY": "test-key"}, clear=True):
            return ConfidentAPIClient()

    def test_conversational_eval_builds_correct_payload(self, client):
        test_cases = [
            {
                "turns": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi there"},
                ],
                "scenario": "greeting",
            }
        ]
        mc = "npc-conversation-quality"

        with patch.object(client, "_request", return_value={"success": True}) as mock_request:
            client.evaluate_conversational(test_cases, mc, identifier="conv-test-1")

        expected_body = {
            "metricCollection": "npc-conversation-quality",
            "conversationalTestCases": [{"scenario": "greeting", "turns": test_cases[0]["turns"]}],
            "identifier": "conv-test-1",
            "hyperparameters": {},
        }
        mock_request.assert_called_once_with("POST", "/evaluate", expected_body)
