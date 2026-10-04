"""Score the agent against eval/cases.yaml."""

import json
import re
import sys
import time
from pathlib import Path

import yaml

from gridcast.agent import run

CASES = yaml.safe_load(Path("eval/cases.yaml").read_text())


def grade(case: dict, result: dict) -> dict:
    names = [c["name"] for c in result["tool_calls"]]
    answer = result["answer"].lower()
    checks = {}

    if "expect_tool" in case:
        checks["tool"] = case["expect_tool"] in names

    if case.get("expect_args"):
        got = result["tool_calls"][0]["input"] if result["tool_calls"] else {}
        checks["args"] = all(got.get(k) == v for k, v in case["expect_args"].items())

    if case.get("expect_value") is not None:
        nums = [float(n.replace(",", ""))
        for n in re.findall(r"\d[\d,]*\.?\d*", result["answer"])]
        tol = case["expect_value"] * case.get("tolerance_pct", 1.0) / 100
        checks["value"] = any(abs(n - case["expect_value"]) <= tol for n in nums)

    for phrase in case.get("must_contain", []):
        checks[f"has:{phrase}"] = str(phrase).lower() in answer
    if case.get("must_contain_any"):
        checks["any_of"] = any(
            str(p).lower() in answer for p in case["must_contain_any"]
        )
    for phrase in case.get("must_not_contain", []):
        checks[f"not:{phrase}"] = str(phrase).lower() not in answer

    return checks


def main() -> None:
    degraded = "--degraded" in sys.argv
    rows = []
    for case in CASES:
        t0 = time.time()
        result = run(case["question"], verbose=False, degraded=degraded)
        checks = grade(case, result)
        rows.append({
            "id": case["id"],
            "passed": all(checks.values()),
            "checks": checks,
            "turns": result["turns"],
            "seconds": round(time.time() - t0, 1),
            "tools": [c["name"] for c in result["tool_calls"]],
            "answer": result["answer"],
        })
        mark = "PASS" if rows[-1]["passed"] else "FAIL"
        print(f"{mark}  {case['id']:<20} {rows[-1]['seconds']:>5}s")
        if not rows[-1]["passed"]:
            failed = [k for k, v in checks.items() if not v]
            print(f"      failed: {', '.join(failed)}")

    n_pass = sum(r["passed"] for r in rows)
    print(f"\n{n_pass}/{len(rows)} passed "
          f"({100 * n_pass / len(rows):.0f}%), "
          f"{sum(r['seconds'] for r in rows):.0f}s total")

    Path("results").mkdir(exist_ok=True)
    name = "eval_degraded.json" if degraded else "eval.json"
    Path(f"results/{name}").write_text(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
