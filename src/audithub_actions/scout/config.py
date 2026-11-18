"""Load Scout's SDK configuration from inline JSON or a workspace file."""

import json
import os
from pathlib import Path

from audithub_sdk import AgentInput, AgentParameters
from pydantic import ValidationError

from audithub_actions.common.inputs import get_input


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Scout config must not contain duplicate JSON keys.")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("Scout config must use valid JSON; NaN and Infinity are not supported.")


def load_config(commit: str) -> AgentInput:
    inline = get_input("scout-config")
    filename = get_input("scout-config-file")
    if bool(inline) == bool(filename):
        raise ValueError("Provide exactly one of scout-config or scout-config-file.")

    if filename:
        path = Path(filename)
        if not path.is_absolute():
            workspace = os.environ.get("GITHUB_WORKSPACE")
            if not workspace:
                raise ValueError(
                    "GITHUB_WORKSPACE is required for relative scout-config-file paths."
                )
            path = Path(workspace) / path
        try:
            inline = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError, ValueError):
            raise ValueError(
                "Could not read scout-config-file as UTF-8. Check the path and check out "
                "the repository (or create the file) before running the action."
            ) from None

    try:
        data = json.loads(inline, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Scout config is not valid JSON (line {exc.lineno}, column {exc.colno})."
        ) from None

    if not isinstance(data, dict):
        raise ValueError("Scout config must be a JSON object.")
    if data.keys() - AgentInput.model_fields.keys():
        raise ValueError(
            "Unsupported Scout config field. Allowed fields: budget, name, parameters."
        )
    parameters = data.setdefault("parameters", {})
    if not isinstance(parameters, dict):
        raise ValueError("Scout config parameters must be a JSON object.")
    if parameters.keys() - AgentParameters.model_fields.keys():
        raise ValueError(
            "Unsupported Scout parameter. "
            "Allowed fields: input_limit, extra_context, generate_pocs."
        )
    budget = data.get("budget")
    if not isinstance(budget, str) or not budget.strip():
        raise ValueError("Scout config budget must be a nonempty string.")
    data["budget"] = budget.strip()
    if data.get("name") is None:
        data["name"] = f"Scout {commit[:12]}"
    try:
        return AgentInput.model_validate(data)
    except ValidationError as exc:
        # Report field paths and expected types without logging configuration values.
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors(include_input=False, include_url=False)
        )
        raise ValueError(f"Invalid Scout config: {problems}") from None
