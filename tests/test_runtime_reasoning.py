import json

import pytest

from powerbi_agent.core import BuildError
from powerbi_agent.reasoning import CommandReasoningAdapter, knowledge
from powerbi_agent.runtime import assess_results, result_scalar, source_expectations


def test_independent_totals_and_filter_context(model, sales):
    checks = source_expectations(model, [sales])
    revenue = next(c for c in checks if c["measure"] == "Total Revenue" and c["context"] == "grand_total")
    margin = next(c for c in checks if c["measure"] == "Margin %" and c["context"] == "grand_total")
    assert revenue["expected"] == 300
    assert margin["expected"] == pytest.approx(130 / 300)
    assert any(c["context"] == "category_filter" for c in checks)
    assert "CALCULATE" in next(c["query"] for c in checks if c["context"] == "category_filter")
    relationship = next(c for c in checks if c["measure"] == "Total Revenue" and c["context"].startswith("relationship_filter"))
    assert "'DimProduct'[ProductId]" in relationship["query"]
    assert relationship["expected"] == 100


def test_runtime_wrong_totals_and_unknown_results_are_not_passed():
    assert assess_results([], [])["status"] == "needs_review"
    checks = [{"has_expected": True, "expected": 100}]
    assert assess_results(checks, [{"content": [{"text": json.dumps({"rows": [{"[Value]": 90}]})}]}])["status"] == "failed"
    assert assess_results(checks, [{"unrecognized": "data"}])["status"] == "needs_review"
    assert assess_results(checks, [{"rows": [[100]]}])["status"] == "passed"


def test_original_knowledge_available_and_planner_rejects_prose(tmp_path, model, report, sales, monkeypatch):
    refs = knowledge()
    assert "references/tmdl-measures.md" in refs
    import powerbi_agent.reasoning as module
    monkeypatch.setattr(module, "run_json", lambda *a, **k: {"text": "Here is your DAX"})
    with pytest.raises(BuildError, match="JSON objects"):
        CommandReasoningAdapter(["planner"]).plan([sales], "Revenue", model, report, tmp_path)
