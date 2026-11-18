# Scout wait

Wait for an existing AuditHub task to succeed and return its finding counts. Only the organization and task IDs are needed to identify the task; this action creates no version or task.

```yaml
- uses: Veridise/audithub-actions/actions/scout/wait@v1
  id: scout
  with:
    client-id: ${{ secrets.AUDITHUB_CLIENT_ID }}
    client-secret: ${{ secrets.AUDITHUB_CLIENT_SECRET }}
    organization-id: ${{ vars.AUDITHUB_ORGANIZATION_ID }}
    task-id: ${{ steps.submit.outputs.task-id }}
```

Examples assume the first `v1` release has been published. Until then, replace `v1` with a commit SHA containing these actions.

## Inputs

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| `client-id` | Yes | — | OIDC client ID. |
| `client-secret` | Yes | — | OIDC client secret. Pass a GitHub Actions secret. |
| `oidc-scope` | No | `openid profile` | OIDC scopes; set empty to omit the scope parameter. |
| `organization-id` | Yes | — | AuditHub organization ID. |
| `task-id` | Yes | — | Existing AuditHub task ID to wait for. |
| `timeout-seconds` | No | `3600` | Maximum wait time in seconds. A timeout does not cancel the remote task. |
| `poll-interval-seconds` | No | `15` | Seconds between task-status requests. |

## Outputs

| Output | Description |
| --- | --- |
| `findings-count` | Total findings reported by the completed task. |
| `findings-by-severity` | JSON object with critical, high, medium, low, warning, and info counts. |

`findings-by-severity` always includes all six severity keys, with zero for absent levels:

```json
{"critical":0,"high":2,"medium":1,"low":0,"warning":0,"info":0}
```

Use `fromJSON(steps.scout.outputs.findings-by-severity).high` to read an individual severity. `findings-count` is the sum of these counters. Counts come from AuditHub's task-level `findings_counters`, matching its task summary; they are not a separate issue/triage count.

Only `Succeeded` produces finding outputs. Failed, errored, canceled, skipped, omitted, or `Finished` tasks fail the action. Missing or unrecognized counters also fail instead of reporting a clean scan. Findings themselves do not fail the action; apply a threshold in your workflow if needed.

The timeout covers polling, retries, and in-flight requests after submission. Set the job's `timeout-minutes` high enough for setup, submission, and this wait. Timeout or workflow cancellation does not cancel the remote scan. You can resume using `scout/wait` with the task ID.

See the [repository README](../../../README.md) for authentication, runner requirements, and complete workflow examples.
