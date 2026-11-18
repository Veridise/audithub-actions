# Scout submit-and-wait

Create an AuditHub project version from an exact Git commit, submit a Scout task, and wait for its findings. Uses the same implementation as the separate submit and wait actions.

```yaml
- uses: Veridise/audithub-actions/actions/scout/submit-and-wait@v1
  id: scout
  with:
    client-id: ${{ secrets.AUDITHUB_CLIENT_ID }}
    client-secret: ${{ secrets.AUDITHUB_CLIENT_SECRET }}
    organization-id: ${{ vars.AUDITHUB_ORGANIZATION_ID }}
    project-id: ${{ vars.AUDITHUB_PROJECT_ID }}
    scout-config: |
      {"budget": ${{ toJSON(vars.AUDITHUB_SCOUT_BUDGET) }}}
    commit: ${{ github.sha }}
```

Examples assume the first `v1` release has been published. Until then, replace `v1` with a commit SHA containing these actions.

## Inputs

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| `client-id` | Yes | — | OIDC client ID. |
| `client-secret` | Yes | — | OIDC client secret. Pass a GitHub Actions secret. |
| `oidc-scope` | No | `openid profile` | OIDC scopes; set empty to omit the scope parameter. |
| `organization-id` | Yes | — | AuditHub organization ID. |
| `project-id` | Yes | — | AuditHub project ID in which to create a version and task. |
| `repository-url` | No | `${{ github.server_url }}/${{ github.repository }}.git` | HTTPS Git repository URL accessible to the AuditHub server. |
| `commit` | No | `${{ github.sha }}` | Full 40-character commit SHA to scan. |
| `scout-config` | One of the two | — | Inline Scout JSON object; mutually exclusive with `scout-config-file`. |
| `scout-config-file` | One of the two | — | UTF-8 JSON file; relative paths resolve from `GITHUB_WORKSPACE`. |
| `version-name` | No | — | Unique project version name. Defaults to scout-<short-sha>-<random-id>. |
| `includes-submodules` | No | `false` | Include Git submodules when AuditHub fetches the commit. |
| `timeout-seconds` | No | `3600` | Maximum wait time in seconds. A timeout does not cancel the remote task. |
| `poll-interval-seconds` | No | `15` | Seconds between task-status requests. |

Provide exactly one configuration input. See [Scout configuration](../../../README.md#scout-configuration) for the JSON schema and file examples.

## Outputs

| Output | Description |
| --- | --- |
| `task-id` | ID of the submitted AuditHub task. |
| `task-url` | AuditHub web link to the task analysis. |
| `findings-count` | Total findings reported by the completed task. |
| `findings-by-severity` | JSON object with critical, high, medium, low, warning, and info counts. |

`findings-by-severity` always includes all six severity keys, with zero for absent levels:

```json
{"critical":0,"high":2,"medium":1,"low":0,"warning":0,"info":0}
```

Use `fromJSON(steps.scout.outputs.findings-by-severity).high` to read an individual severity. `findings-count` is the sum of these counters. Counts come from AuditHub's task-level `findings_counters`, matching its task summary; they are not a separate issue/triage count.

Only `Succeeded` produces finding outputs. Failed, errored, canceled, skipped, omitted, or `Finished` tasks fail the action. Missing or unrecognized counters also fail instead of reporting a clean scan. Findings themselves do not fail the action; apply a threshold in your workflow if needed.

The timeout covers polling, retries, and in-flight requests after submission. Set the job's `timeout-minutes` high enough for setup, submission, and this wait. Timeout or workflow cancellation does not cancel the remote scan. You can resume using `scout/wait` with the task ID.

Each invocation creates a new version and task. The default version name includes a random suffix so reruns do not collide; a custom `version-name` must be unique within the project. Resource-creation requests are not automatically retried. If a response is lost or submission fails after version creation, inspect AuditHub before rerunning; the version is not automatically deleted.

AuditHub fetches the repository server-side at `commit`; local modifications are not uploaded. A checkout is only needed when reading a checked-in configuration file. The server must have access to the repository and requested commit. This action does not forward the workflow's GitHub token. For pull requests from forks, supply both the head repository URL and head SHA explicitly.

The task ID and URL are written as soon as submission succeeds, before polling. If waiting fails, they are also available in the step log; use `continue-on-error` and an appropriate subsequent-step condition when handling failures in a workflow.

See the [repository README](../../../README.md) for authentication, runner requirements, and complete workflow examples.
