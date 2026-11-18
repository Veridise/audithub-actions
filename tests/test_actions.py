"""Check public action contracts and invocation from a consumer checkout."""

import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def manifests():
    return {
        name: yaml.safe_load((ROOT / "actions" / "scout" / name / "action.yml").read_text())
        for name in ("submit", "wait", "submit-and-wait")
    }


def test_public_outputs_and_combined_contract():
    actions = manifests()
    assert set(actions["submit"]["outputs"]) == {"task-id", "task-url"}
    assert set(actions["wait"]["outputs"]) == {"findings-count", "findings-by-severity"}
    assert actions["submit-and-wait"]["outputs"] == (
        actions["submit"]["outputs"] | actions["wait"]["outputs"]
    )


@pytest.mark.parametrize("operation", ["submit", "wait", "submit-and-wait"])
def test_inputs_are_mapped_through_environment(operation):
    action = manifests()[operation]
    assert action["runs"]["using"] == "composite"
    step = action["runs"]["steps"][-1]
    for name in action["inputs"]:
        assert step["env"]["AH_" + name.upper().replace("-", "_")] == ("${{ inputs." + name + " }}")
    assert "${{" not in step["run"]
    assert step["id"] == "scout"


@pytest.mark.parametrize("operation", ["submit", "wait", "submit-and-wait"])
def test_runner_uses_action_source_from_other_directory(operation, tmp_path):
    # An unrelated checkout, including spaces, must not control the installed Python project.
    consumer = tmp_path / "consumer checkout"
    consumer.mkdir()
    (consumer / "pyproject.toml").write_text("THIS MUST NOT BE USED")
    binaries = tmp_path / "bin"
    binaries.mkdir()
    uv = binaries / "uv"
    uv.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$UV_PROJECT_ENVIRONMENT" "$@"\n')
    uv.chmod(0o755)
    action_path = ROOT / "actions" / "scout" / operation
    step = manifests()[operation]["runs"]["steps"][-1]
    result = subprocess.run(
        ["bash", "-e", "-c", step["run"]],
        cwd=consumer,
        env={
            **os.environ,
            "ACTION_PATH": str(action_path),
            "RUNNER_TEMP": str(tmp_path),
            "PATH": f"{binaries}:{os.environ['PATH']}",
        },
        check=True,
        text=True,
        capture_output=True,
    )
    environment, *args = result.stdout.splitlines()
    assert args == [
        "run",
        "--directory",
        str(ROOT),
        "--project",
        str(ROOT),
        "--locked",
        "--no-dev",
        "--python",
        "3.12",
        "-m",
        "audithub_actions.scout",
        operation,
    ]
    assert not Path(environment).parent.exists()  # Temporary environment is cleaned up.


def test_workflows_and_examples_parse():
    for path in [*ROOT.glob(".github/workflows/*.yml"), *ROOT.glob("examples/*.yml")]:
        workflow = yaml.safe_load(path.read_text())
        assert workflow["jobs"], path
        # PyYAML interprets the YAML 1.1 spelling 'on' as a boolean.
        assert "on" in workflow or True in workflow, path
        for job in workflow["jobs"].values():
            for step in job.get("steps", []):
                if "uses" in step and step["uses"].startswith("Veridise/audithub-actions/"):
                    operation = step["uses"].split("@", 1)[0].rsplit("/", 1)[-1]
                    action = manifests()[operation]
                    assert set(step.get("with", {})) <= set(action["inputs"])
                    if operation != "wait":
                        assert (
                            len({"scout-config", "scout-config-file"} & step.get("with", {}).keys())
                            == 1
                        )
                    for name, spec in action["inputs"].items():
                        if spec.get("required") and "default" not in spec:
                            assert name in step.get("with", {}), (path, name)
                if "run" in step:
                    assert not re.search(r"\$\{\{\s*secrets\.", step["run"])
