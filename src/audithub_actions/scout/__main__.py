"""Entry point shared by the three Scout action wrappers."""

import argparse
import asyncio
import json

import httpx
from audithub_sdk import TasksApi, ToolsApi, VersionsApi
from audithub_sdk.exceptions import ApiException
from pydantic import ValidationError

from audithub_actions.common.client import create_client
from audithub_actions.common.config import AUDITHUB_WEB_URL
from audithub_actions.common.github import report_error, write_outputs
from audithub_actions.common.inputs import positive_integer
from audithub_actions.common.tasks import TaskFailed, wait_for_task
from audithub_actions.scout.submit import Submission, submit


async def run(operation: str) -> None:
    organization_id = positive_integer("organization-id")
    request = Submission.from_inputs(organization_id) if operation != "wait" else None
    task_id = positive_integer("task-id") if operation == "wait" else None
    # Validate wait settings before creating a remote task in submit-and-wait.
    if operation != "submit":
        timeout = positive_integer("timeout-seconds", "3600")
        poll_interval = positive_integer("poll-interval-seconds", "15")

    async with create_client() as client:
        if request is not None:
            task_id = await submit(VersionsApi(client), ToolsApi(client), request)
            task_url = (
                f"{AUDITHUB_WEB_URL}/app/organizations/{organization_id}"
                f"/projects/{request.project_id}/tasks/{task_id}/analysis"
            )
            # Publish immediately, so a later wait failure still leaves the task traceable.
            write_outputs({"task-id": task_id, "task-url": task_url})
            print(f"Submitted AuditHub task {task_id}: {task_url}", flush=True)
        if operation != "submit":
            assert task_id is not None
            counts = await wait_for_task(
                TasksApi(client),
                organization_id,
                task_id,
                timeout_seconds=timeout,
                poll_interval_seconds=poll_interval,
            )
            write_outputs(
                {
                    "findings-count": sum(counts.values()),
                    "findings-by-severity": json.dumps(counts, separators=(",", ":")),
                }
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("submit", "wait", "submit-and-wait"))
    args = parser.parse_args()
    try:
        asyncio.run(run(args.operation))
    except ValidationError:
        report_error("AuditHub SDK validation failed. Check inputs and API/SDK compatibility.")
        return 1
    except ApiException as exc:
        # API exception strings can contain response bodies, credentials, or submitted context.
        report_error(f"AuditHub API request failed (HTTP {exc.status}). Check access and inputs.")
        return 1
    except httpx.HTTPError:
        report_error(
            "AuditHub connection or authentication failed. "
            "Check service availability and credentials."
        )
        return 1
    except (TaskFailed, TimeoutError, ValueError) as exc:
        report_error(str(exc))
        return 1
    except Exception:
        report_error("Unexpected AuditHub action error. No request or response data was logged.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
