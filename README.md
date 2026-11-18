# audithub-actions

GitHub Actions for AuditHub, implemented with [audithub-sdk 1.0.3](https://github.com/Veridise/audithub-sdk/tree/v1.0.3).

## Scout actions

| Action | Behavior | Outputs |
| --- | --- | --- |
| [scout/submit](actions/scout/submit/README.md) | Submit a scan of a Git commit. | `task-id`, `task-url` |
| [scout/wait](actions/scout/wait/README.md) | Wait for an existing task to succeed. | `findings-count`, `findings-by-severity` |
| [scout/submit-and-wait](actions/scout/submit-and-wait/README.md) | Submit and wait in one step. | All four outputs |

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

- name: Display finding counts
  env:
    FINDINGS: ${{ steps.scout.outputs.findings-count }}
    SEVERITIES: ${{ steps.scout.outputs.findings-by-severity }}
  run: |
    printf 'Findings: %s\n' "$FINDINGS"
    printf 'By severity: %s\n' "$SEVERITIES"
```

Examples assume a published `v1` release. Before the first release, replace `v1` with a repository commit containing these actions. Action releases are independent of the SDK version.

Complete examples: [one combined action](examples/scout.yml), [configuration from a file](examples/scout-from-file.yml), and [submit and wait in separate jobs](examples/scout-separate-jobs.yml).

## Scout configuration

`submit` and `submit-and-wait` require exactly one of `scout-config` (inline JSON) or `scout-config-file` (a JSON file). These replace the separate `budget`, `task-name`, `paths`, `extra-context`, and `generate-pocs` inputs. Authentication, organization/project, source repository/commit, version creation, and wait settings remain action inputs. `wait` only monitors an existing task and takes no Scout configuration.

The object follows the SDK's `AgentInput` shape:

```json
{
  "budget": "YOUR_SCOUT_BUDGET_CLASS",
  "name": "Review contracts",
  "parameters": {
    "input_limit": ["src/", "contracts/"],
    "extra_context": "Focus on access control and withdrawals.",
    "generate_pocs": true
  }
}
```

| JSON field | Required | Default | Description |
| --- | --- | --- | --- |
| `budget` | Yes | — | Nonempty name of a Scout budget class configured in AuditHub. |
| `name` | No | `Scout <short-sha>` | Task name. |
| `parameters` | No | `{}` | Scout parameters supported by SDK 1.0.3. |
| `parameters.input_limit` | No | No path restriction | Array of paths to include in the scan. |
| `parameters.extra_context` | No | No additional context | Additional instructions or context for Scout. |
| `parameters.generate_pocs` | No | `false` | JSON boolean requesting proofs of concept. |

The minimum configuration is `{"budget":"YOUR_SCOUT_BUDGET_CLASS"}`. Unknown fields, duplicate keys, invalid JSON, and incorrect field types fail before any AuditHub requests. The action does not interpret expressions inside a configuration file.

For inline configuration, use a YAML block containing JSON:

```yaml
    scout-config: |
      {
        "budget": ${{ toJSON(vars.AUDITHUB_SCOUT_BUDGET) }},
        "parameters": {
          "input_limit": ["src/", "contracts/"],
          "generate_pocs": true
        }
      }
```

Action inputs are strings, so pass JSON text rather than a YAML mapping. Use [`toJSON`](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions#tojson) when inserting an expression into JSON, or to serialize an existing object such as `scout-config: ${{ toJSON(matrix.scout) }}`. A variable already containing complete JSON can be passed directly: `scout-config: ${{ vars.SCOUT_CONFIG }}`.

For a configuration file, save the object as `.github/scout.json` in the calling repository, then check out the repository before the Scout action:

```yaml
- uses: actions/checkout@8f4b7f84864484a7bf31766abe9204da3cbe65b3 # v6.2.0
- uses: Veridise/audithub-actions/actions/scout/submit-and-wait@v1
  id: scout
  with:
    client-id: ${{ secrets.AUDITHUB_CLIENT_ID }}
    client-secret: ${{ secrets.AUDITHUB_CLIENT_SECRET }}
    organization-id: ${{ vars.AUDITHUB_ORGANIZATION_ID }}
    project-id: ${{ vars.AUDITHUB_PROJECT_ID }}
    commit: ${{ github.sha }}
    scout-config-file: .github/scout.json
```

Relative paths resolve from `GITHUB_WORKSPACE`, even if the job sets a different working directory. Absolute paths are also supported. The file must exist on the runner before the action starts; it can come from checkout or an earlier step. See the [sample JSON](examples/scout-config.json) and [complete file workflow](examples/scout-from-file.yml). Copy the sample to `.github/scout.json` and replace its budget placeholder with an available budget class.

## Setup and behavior

- Use a Linux runner with Bash (the CI target is `ubuntu-latest`). The actions install uv and Python 3.12, then install the shared package using `uv.lock` in a temporary virtual environment.
- Configure an AuditHub OIDC service client with access to the organization/project, permission to create versions and Scout tasks, and permission to read task details. Store its credentials in GitHub Actions secrets. Authentication uses the SDK's OIDC client-credentials helper and token refresh; it does not use GitHub OIDC federation.
- The actions use the hosted AuditHub API at `https://app.audithub.dev/api/v1` and OIDC discovery at `https://sso.veridise.com/auth/realms/veridise/.well-known/openid-configuration`. These service endpoints are fixed; users do not configure them. Task links point to `https://app.audithub.dev`.
- Provide an existing organization/project and an available Scout budget class. The action does not create projects or choose a budget on your behalf.
- Submission defaults to the workflow repository URL and `github.sha`. Supply `repository-url` and a full 40-character `commit` SHA to scan another repository or commit. AuditHub fetches this source remotely. A checkout is only needed when reading a checked-in configuration file. The repository and commit must be accessible to AuditHub; the workflow's GitHub token is not forwarded.
- Each submission creates a uniquely named version and one task. Submission errors can leave a created version or, after a lost response, a running task. Check AuditHub before retrying an ambiguous submission.
- Successful waits return task-level finding counters, including zero values for `critical`, `high`, `medium`, `low`, `warning`, and `info`. Findings do not automatically fail a workflow. Use `fromJSON` on the JSON output to enforce your own thresholds.
- Unsuccessful task states and wait timeouts fail the action. The default wait is 3,600 seconds with 15-second polling. A wait timeout does not cancel the AuditHub task; run `scout/wait` to resume. Choose a job timeout that also allows time for setup and submission.

## Repository layout

```text
actions/scout/{submit,wait,submit-and-wait}/  Action manifests and documentation
src/audithub_actions/common/                SDK authentication, inputs, outputs, polling
src/audithub_actions/scout/                 Scout submission and action entry point
scripts/run-action.sh                      Runtime setup and invocation
tests/                                     SDK/HTTP and action contract tests
examples/                                  Consumer workflows
.github/workflows/                         Repository CI
pyproject.toml                             Shared dependencies and tooling
uv.lock                                    Locked dependencies
```

Action manifests map inputs through environment variables. The shared launcher resolves code relative to the downloaded action's `github.action_path`, allowing it to run from any consumer repository. The combined action invokes the same Python submission and polling functions, with no second setup or cross-version action references.

## Development

```sh
uv sync --locked --python 3.12
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest
```

Tests use the installed SDK with mocked HTTP transport, covering wire requests, OIDC refresh, task states, deadlines, output contracts, and invocation from a separate checkout. They create no live AuditHub resources. A live integration run still requires credentials and a reachable repository/project.
