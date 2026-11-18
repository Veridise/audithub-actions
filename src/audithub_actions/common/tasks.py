"""Poll task state with an overall deadline and bounded transient retries."""

import asyncio

import httpx
from audithub_sdk import TasksApi
from audithub_sdk.exceptions import ApiException

ACTIVE_STATUSES = {"Queued", "Pending", "Running"}
SEVERITIES = ("critical", "high", "medium", "low", "warning", "info")


class TaskFailed(RuntimeError):
    """The remote task terminated without succeeding."""


async def wait_for_task(
    tasks: TasksApi,
    organization_id: int,
    task_id: int,
    *,
    timeout_seconds: int,
    poll_interval_seconds: int,
) -> dict[str, int]:
    try:
        async with asyncio.timeout(timeout_seconds):
            while True:
                try:
                    task = await tasks.get_info_organizations_organization_id_tasks_task_id_get(
                        organization_id=organization_id,
                        task_id=task_id,
                        _request_timeout=30,
                    )
                except ApiException as exc:
                    if exc.status not in {429, 500, 502, 503, 504}:
                        raise
                    print("Temporary AuditHub error; retrying task status.", flush=True)
                except httpx.TransportError:
                    print("Temporary connection error; retrying task status.", flush=True)
                else:
                    print(f"AuditHub task {task_id}: {task.status}", flush=True)
                    if task.status == "Succeeded":
                        if task.findings_counters is None:
                            raise ValueError("The completed task did not include finding counts.")
                        counts = dict.fromkeys(SEVERITIES, 0)
                        for severity, count in task.findings_counters.items():
                            if severity not in counts or count < 0:
                                raise ValueError("AuditHub returned invalid finding counts.")
                            counts[severity] = count
                        return counts
                    if task.status not in ACTIVE_STATUSES:
                        raise TaskFailed(
                            f"AuditHub task {task_id} ended with status {task.status}."
                        )
                await asyncio.sleep(poll_interval_seconds)
    except TimeoutError as exc:
        raise TimeoutError(
            f"Timed out after {timeout_seconds} seconds waiting for AuditHub task {task_id}. "
            "The remote task was not canceled; use scout/wait to resume waiting."
        ) from exc
