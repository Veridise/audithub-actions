# Scout submit

Create an AuditHub project version from an exact Git commit and submit a Scout task. Returns immediately after AuditHub accepts the task.

```yaml
- uses: Veridise/audithub-actions/actions/scout/submit@v1
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

Provide exactly one configuration input. See [Scout configuration](../../../README.md#scout-configuration) for the JSON schema and file examples.

## Outputs

| Output | Description |
| --- | --- |
| `task-id` | ID of the submitted AuditHub task. |
| `task-url` | AuditHub web link to the task analysis. |

Each invocation creates a new version and task. The default version name includes a random suffix so reruns do not collide; a custom `version-name` must be unique within the project. Resource-creation requests are not automatically retried. If a response is lost or submission fails after version creation, inspect AuditHub before rerunning; the version is not automatically deleted.

AuditHub fetches the repository server-side at `commit`; local modifications are not uploaded. A checkout is only needed when reading a checked-in configuration file. The server must have access to the repository and requested commit. This action does not forward the workflow's GitHub token. For pull requests from forks, supply both the head repository URL and head SHA explicitly.

See the [repository README](../../../README.md) for authentication, runner requirements, and complete workflow examples.
