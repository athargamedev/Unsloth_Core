from scripts.dataset_eval import summarize_deepeval_result


def test_dataset_eval_summary_extracts_metric_failures():
    result = {
        "identifier": "unit-run",
        "testCases": [
            {
                "name": "history_guide:teaching:1",
                "input": "User message",
                "actualOutput": "Generic answer",
                "success": False,
                "metadata": {
                    "npc_key": "history_guide",
                    "category": "teaching",
                    "concept": "cause and effect",
                    "source_path": "subjects/datasets/history_guide/template/train_clean.jsonl",
                    "line_number": 1,
                },
                "metricsData": [
                    {
                        "name": "Persona and Category Fit [GEval]",
                        "score": 0.8,
                        "threshold": 0.75,
                        "success": True,
                        "reason": "ok",
                        "evaluationModel": "qwen2.5:7b (Ollama)",
                    },
                    {
                        "name": "Training Usefulness and Specificity [GEval]",
                        "score": 0.4,
                        "threshold": 0.7,
                        "success": False,
                        "reason": "too generic",
                        "evaluationModel": "qwen2.5:7b (Ollama)",
                    },
                ],
            },
            {
                "name": "history_guide:refusal:2",
                "success": True,
                "metadata": {"category": "refusal"},
                "metricsData": [
                    {
                        "name": "Persona and Category Fit [GEval]",
                        "score": 0.9,
                        "threshold": 0.75,
                        "success": True,
                    }
                ],
            },
        ],
    }

    summary, failures = summarize_deepeval_result(
        result,
        npc_key="history_guide",
        technique="template",
        judge_model="qwen2.5:7b",
        command=["deepeval", "test", "run"],
    )

    assert summary["total"] == 2
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert summary["pass_rate"] == 0.5
    assert summary["categories"]["teaching"]["pass_rate"] == 0.0
    assert summary["categories"]["refusal"]["pass_rate"] == 1.0
    assert summary["metrics"]["Training Usefulness and Specificity [GEval]"]["average_score"] == 0.4
    assert len(failures) == 1
    assert failures[0]["metric"]["reason"] == "too generic"
    assert failures[0]["metadata"]["concept"] == "cause and effect"
