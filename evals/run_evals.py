# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml"]
# ///
"""Run crdb-cookbooks skill evaluations.

For each scenario in scenarios.yaml:
  1. Create a temp workspace with the scenario's fixture files.
  2. Run a headless `claude -p` session there with this repo loaded as a
     plugin, using the model under test (default: claude-opus-4-8).
  3. Have an LLM judge (default: claude-opus-4-8) score the transcript
     against the scenario rubric, returning strict JSON.

Usage:
    uv run evals/run_evals.py                       # all scenarios
    uv run evals/run_evals.py --only hybrid-rrf     # one scenario
    uv run evals/run_evals.py --model claude-opus-4-8 --judge-model claude-opus-4-8
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = REPO_ROOT / "evals" / "scenarios.yaml"
RESULTS_DIR = REPO_ROOT / "evals" / "results"

JUDGE_PROMPT = """You are grading an AI coding agent's transcript against a rubric.

The agent was given this task:
<task>
{prompt}
</task>

The agent produced this response:
<response>
{response}
</response>

Grade the response against each rubric criterion. Be strict: a criterion
passes only if the response clearly satisfies it, not if it is merely
plausible or partially addressed.

Rubric:
{rubric}

Reply with ONLY a JSON object, no markdown fences, in this exact shape:
{{"criteria": [{{"id": 1, "pass": true, "note": "one sentence"}}, ...],
  "overall_pass": true}}
overall_pass is true only if every criterion passes.
"""


def run_agent(prompt: str, fixtures: dict[str, str], model: str, timeout: int) -> str:
    with tempfile.TemporaryDirectory(prefix="crdb-eval-") as workdir:
        for rel_path, content in (fixtures or {}).items():
            path = Path(workdir) / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        result = subprocess.run(
            [
                "claude", "-p", prompt,
                "--model", model,
                "--plugin-dir", str(REPO_ROOT),
                "--permission-mode", "bypassPermissions",
            ],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    if result.returncode != 0:
        raise RuntimeError(f"agent run failed: {result.stderr.strip()[:500]}")
    return result.stdout.strip()


def judge(prompt: str, response: str, rubric: list[str], model: str, timeout: int) -> dict:
    rubric_text = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(rubric))
    judge_input = JUDGE_PROMPT.format(prompt=prompt, response=response, rubric=rubric_text)
    result = subprocess.run(
        ["claude", "-p", judge_input, "--model", model],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"judge run failed: {result.stderr.strip()[:500]}")
    raw = result.stdout.strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise RuntimeError(f"judge returned no JSON: {raw[:300]}")
    return json.loads(match.group(0))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="claude-opus-4-8", help="model under test")
    parser.add_argument("--judge-model", default="claude-opus-4-8", help="judge model")
    parser.add_argument("--only", help="run a single scenario id")
    parser.add_argument("--timeout", type=int, default=900, help="per-run timeout (s)")
    args = parser.parse_args()

    scenarios = yaml.safe_load(SCENARIOS.read_text())
    if args.only:
        scenarios = [s for s in scenarios if s["id"] == args.only]
        if not scenarios:
            print(f"no scenario named {args.only!r}", file=sys.stderr)
            return 2

    results = []
    for scenario in scenarios:
        sid = scenario["id"]
        print(f"[{sid}] running agent ({args.model})...", flush=True)
        try:
            response = run_agent(
                scenario["prompt"], scenario.get("fixtures"), args.model, args.timeout
            )
            print(f"[{sid}] judging ({args.judge_model})...", flush=True)
            verdict = judge(
                scenario["prompt"], response, scenario["rubric"],
                args.judge_model, args.timeout,
            )
            passed = bool(verdict.get("overall_pass"))
            results.append(
                {"id": sid, "pass": passed, "verdict": verdict, "response": response}
            )
        except Exception as exc:
            results.append({"id": sid, "pass": False, "error": str(exc)})
            print(f"[{sid}] ERROR: {exc}", file=sys.stderr, flush=True)

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = RESULTS_DIR / f"{stamp}.json"
    out.write_text(json.dumps(
        {"model": args.model, "judge_model": args.judge_model, "results": results},
        indent=2,
    ))

    print(f"\n{'scenario':<22} result")
    print("-" * 34)
    for r in results:
        status = "PASS" if r["pass"] else "FAIL"
        print(f"{r['id']:<22} {status}")
        for c in r.get("verdict", {}).get("criteria", []):
            if not c.get("pass"):
                print(f"{'':<22}   ✗ {c.get('note', '')}")
    passed = sum(r["pass"] for r in results)
    print(f"\n{passed}/{len(results)} passed — details in {out.relative_to(REPO_ROOT)}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
