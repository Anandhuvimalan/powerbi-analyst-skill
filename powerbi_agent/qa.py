"""Bounded vision-review protocol; scores require actual screenshots and a reviewer."""
from __future__ import annotations

import copy
import math
from pathlib import Path

from .adapters import run_json
from .core import BuildError, write_json
from .report import literal
from .validation import enforce, validate_report

DIMENSIONS = ["layout", "readability", "visual_hierarchy", "color_usage", "data_storytelling"]


class CommandVisionReviewer:
    """Configured trusted vision executable: argv + request.json, returns JSON on stdout."""
    def __init__(self, command):
        if not isinstance(command, list) or not command or not all(isinstance(s, str) for s in command):
            raise BuildError("qa.reviewer_command must be a nonempty executable argument array.")
        self.command = command

    def review(self, request, directory):
        path = directory / "review-request.json"
        write_json(path, request)
        return run_json(self.command + [str(path)], timeout=180)


def visual_qa(state, project, report_plan, model_plan, desktop, reviewer, rerender, directory, maximum=3, threshold=90, pid=None):
    if not 1 <= maximum <= 10 or not 0 <= threshold <= 100:
        raise BuildError("QA requires max_iterations between 1 and 10 and threshold between 0 and 100.")
    selected = desktop.select_pid(project, pid)
    current = copy.deepcopy(report_plan)
    for iteration in range(1, maximum + 1):
        folder = directory / f"iteration-{iteration}"
        folder.mkdir(parents=True, exist_ok=True)
        screenshots = []
        for page in current["pages"]:
            target = folder / (page["name"] + ".png")
            desktop.screenshot(page["name"], selected, target)
            screenshots.append(str(target))
        state.screenshots.extend(screenshots)
        state.iteration_count = iteration
        result = reviewer.review({"screenshots": screenshots, "report_plan": current, "business_objective": state.business_objective,
            "rubric": DIMENSIONS, "checklist": ["overlap", "truncated text", "visual errors", "blank results", "padding", "labels", "axis readability", "legend", "density", "number formats", "contrast"],
            "response_contract": {"scores": "all rubric dimensions, numeric 0..100", "issues": "list of detected issues",
                "patches": "list of {page, visual_index, position?, title?}; position and title changes only", "blocking_issues": "boolean"}}, folder)
        scores = result.get("scores", {})
        if any(isinstance(scores.get(k), bool) or not isinstance(scores.get(k), (int, float)) or not math.isfinite(scores[k]) or not 0 <= scores[k] <= 100 for k in DIMENSIONS):
            raise BuildError("Vision reviewer returned missing/invalid scores; no quality pass was recorded.")
        scores["overall"] = round(sum(scores[k] for k in DIMENSIONS) / len(DIMENSIONS), 1)
        state.qa_scores.append({"iteration": iteration, **scores, "evidence": "screenshot_review"})
        write_json(folder / "review.json", result)
        state.log("QA", f"Screenshot review score {scores['overall']}")
        if scores["overall"] >= threshold and result.get("blocking_issues") is False:
            return {"check": "visual_qa", "status": "passed", "iterations": iteration, "scores": scores}, current
        if iteration == maximum or not result.get("patches"):
            return {"check": "visual_qa", "status": "needs_review", "iterations": iteration, "scores": scores}, current
        candidate = copy.deepcopy(current)
        for patch in result["patches"]:
            if set(patch) - {"page", "visual_index", "position", "title"}:
                raise BuildError("Vision patch contains unsupported changes; only title and geometry can be applied.")
            page = next((p for p in candidate["pages"] if p["name"] == patch["page"]), None)
            index = patch["visual_index"]
            if page is None or not isinstance(index, int) or index < 0 or index >= len(page["visuals"]):
                raise BuildError("Vision patch references a missing visual.")
            for key in ["position", "title"]:
                if key in patch:
                    page["visuals"][index][key] = patch[key]
            if "title" in patch:
                visual = page["visuals"][index]
                if visual["type"] == "textbox" and "text" in visual:
                    visual["text"] = patch["title"]
                else:
                    title = visual.setdefault("container_objects", {}).setdefault("title", [{"properties": {}}])
                    for entry in title:
                        entry.setdefault("properties", {})["text"] = literal(patch["title"])
        enforce(validate_report(candidate, model_plan))
        rerender(candidate)  # Each refinement gets its own staged validation and checkpoint.
        current = candidate
        desktop.reload(selected)
    raise AssertionError("Bounded QA loop terminated unexpectedly")
