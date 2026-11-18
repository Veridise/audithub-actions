"""Write outputs and escaped log commands using GitHub's runner protocol."""

import os
import re
from pathlib import Path


def write_outputs(outputs: dict[str, str | int]) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        raise ValueError("GITHUB_OUTPUT must point to a runner output file.")
    lines = []
    for key, value in outputs.items():
        text = str(value)
        if not re.fullmatch(r"[a-z][a-z0-9-]*", key) or "\n" in text or "\r" in text:
            raise ValueError("Invalid action output.")
        lines.append(f"{key}={text}\n")
    with Path(path).open("a", encoding="utf-8") as output:
        output.writelines(lines)


def escape_command(message: str) -> str:
    return message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def report_error(message: str) -> None:
    print(f"::error::{escape_command(message)}", flush=True)
