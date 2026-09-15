"""Real Microsoft MCP/TOM + PBIR schema integration test on an isolated demo."""
import argparse
import asyncio
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from powerbi_agent.adapters import ModelingMCPAdapter
from powerbi_agent.core import write_json
from powerbi_agent.model import TmdlWriter
from powerbi_agent.orchestrator import build, load_request
from powerbi_agent.transaction import ProjectTransaction


def main():
    args = argparse.ArgumentParser()
    args.add_argument("--remote-schema", action="store_true")
    args.add_argument("--output", default="../output/McpSales/McpSales.pbip", help="Target path relative to examples/")
    options = args.parse_args()
    root = Path(__file__).resolve().parents[1]
    request = load_request(root / "examples/sales-request.json")
    request["modeling"] = {"mode": "mcp"}
    request["remote_schema"] = options.remote_schema
    request["output"] = options.output
    state = build(request, root / "examples")
    # Verify string properties survived TOM deserialization without becoming quoted source names.
    project = Path(state.project_path)
    model = project.parent / (project.stem + ".SemanticModel") / "definition"
    sales_tmdl = (model / "tables/sales.tmdl").read_text(encoding="utf-8-sig")
    assert "sourceColumn: OrderId" in sales_tmdl and "sourceColumn: 'OrderId'" not in sales_tmdl
    assert "measure 'Total Revenue'" in sales_tmdl
    advanced = copy.deepcopy(state.model_plan)
    advanced["expressions"] = [{"name": "ReportingYear", "expression": '2025 meta [IsParameterQuery=true, Type="Number", IsParameterQueryRequired=true]'}]
    advanced["calculation_groups"] = [{"name": "Time Intelligence", "precedence": 20, "items": [
        {"name": "Current", "expression": "SELECTEDMEASURE()"},
        {"name": "Previous Year", "expression": "CALCULATE(SELECTEDMEASURE(), DATEADD('DimDate'[Date], -1, YEAR))", "format_expression": "SELECTEDMEASUREFORMATSTRING()"}]}]
    advanced["roles"] = [{"name": "North", "filters": {"sales": '[Region] = "North"'}}]
    advanced_folder = root / "output/advanced-model"
    TmdlWriter().apply(advanced_folder, advanced)
    evidence = asyncio.run(ModelingMCPAdapter().verify_folder(advanced_folder / "definition"))
    write_json(root / "output/integration-evidence.json", {"project": state.project_path,
        "validation": state.validation_results, "advanced_model_tom_parse": evidence,
        "runtime": "Not exercised by this script; see the project run's runtime-results.json",
        "visual": "Not exercised by this script; see output/McpSales/screenshots and docs/demo.md"})
    print("Real MCP measure execution, canonical source bindings, advanced TMDL parse and report validation completed.")


if __name__ == "__main__":
    main()
