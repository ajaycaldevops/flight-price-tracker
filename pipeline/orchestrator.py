#!/usr/bin/env python3
"""
SDLC Pipeline Orchestrator
Runs 4 Claude Code slash commands in sequence via `claude -p`.
No API key needed — uses your Claude Code Pro subscription.

Usage:
  python pipeline/orchestrator.py --project my-tool
  python pipeline/orchestrator.py --project my-tool --skip-permissions
"""
import sys
import os
import datetime
import subprocess
import argparse

COMMANDS = ["pipeline-req", "pipeline-build", "pipeline-test", "pipeline-deploy"]
RUNS_DIR = os.path.join(os.path.dirname(__file__), "runs")


def run_agent(cmd, workspace, skip_permissions=False):
    args = ["claude", "-p", f"/{cmd} {workspace}"]
    if skip_permissions:
        args.append("--dangerously-skip-permissions")
    print(f"\n-- {cmd.upper()} --")
    result = subprocess.run(args)
    return result.returncode == 0


def run(config=None, skip_permissions=False):
    config = config or {}
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    workspace = os.path.join(RUNS_DIR, f"{ts}_{config.get('project', 'project')}")
    os.makedirs(workspace, exist_ok=True)
    workspace = os.path.abspath(workspace)

    # write mock inputs if provided by harness
    if "mock_answers" in config:
        lines = []
        questions = [
            "What do you want to build?",
            "Language and library constraints?",
            "Exact inputs and outputs?",
            "Edge cases to handle?",
        ]
        for q, a in zip(questions, config["mock_answers"]):
            lines.append(f"Q: {q}\nA: {a}\n")
        with open(os.path.join(workspace, "mock_inputs.md"), "w") as f:
            f.write("\n".join(lines))

    print(f"Workspace: {workspace}")

    for cmd in COMMANDS:
        if not run_agent(cmd, workspace, skip_permissions):
            print(f"\nPipeline halted at {cmd}.")
            return False

    print(f"\nPipeline complete -> {workspace}")
    return True


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--project", default="project")
    p.add_argument("--skip-permissions", action="store_true",
                   help="Pass --dangerously-skip-permissions to claude (for CI/harness use)")
    args = p.parse_args()
    sys.exit(0 if run({"project": args.project}, args.skip_permissions) else 1)
