"""Exercise the installed SDK's serialization, authentication, and response models."""

import asyncio
import json
from urllib.parse import parse_qs

import httpx
import pytest
from audithub_sdk_ext import AuthenticatedApiClient

from audithub_actions.common import client as client_module
from audithub_actions.common.github import write_outputs
from audithub_actions.common.tasks import TaskFailed
from audithub_actions.scout.__main__ import main, run

SHA = "a" * 40


def task_response(status="Succeeded", counts=None):
    return {
        "id": 42,
        "tool_name": "agent",
        "tool_version": "1",
        "version_id": 7,
        "status": status,
        "created_at": "2026-01-01T00:00:00Z",
        "created_by": "test-user",
        "findings_counters": counts if counts is not None else {},
    }


@pytest.fixture
def environment(monkeypatch, tmp_path):
    inputs = {
        "client-id": "test-client",
        "client-secret": "test-secret",
        "organization-id": "1",
        "project-id": "2",
        "repository-url": "https://github.com/example/contracts.git",
        "commit": SHA,
        "scout-config": '{"budget":"test-budget"}',
        "task-id": "42",
        "timeout-seconds": "10",
        "poll-interval-seconds": "1",
    }
    # Keep local user credentials and parameters out of these tests.
    import os

    for key in os.environ:
        if key.startswith("AH_"):
            monkeypatch.delenv(key)
    for key, value in inputs.items():
        monkeypatch.setenv("AH_" + key.upper().replace("-", "_"), value)
    output = tmp_path / "outputs"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    return output


@pytest.fixture
def sdk_server(monkeypatch):
    requests = []
    responses = []

    def handler(request):
        requests.append(request)
        if request.url.host == "sso.veridise.com":
            if request.method == "GET":
                assert str(request.url) == (
                    "https://sso.veridise.com/auth/realms/veridise/.well-known/openid-configuration"
                )
                return httpx.Response(
                    200,
                    json={
                        "token_endpoint": "https://sso.veridise.com/auth/realms/veridise/protocol/openid-connect/token"
                    },
                )
            assert parse_qs(request.content.decode())["client_secret"] == ["test-secret"]
            return httpx.Response(200, json={"access_token": "mock-access-token"})
        assert request.url.host == "app.audithub.dev"
        assert request.url.path.startswith("/api/v1/")
        assert request.headers["Authorization"] == "Bearer mock-access-token"
        assert responses, f"Unexpected SDK request: {request.method} {request.url}"
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return httpx.Response(response[0], json=response[1])

    transport = httpx.MockTransport(handler)

    def http_factory(**kwargs):
        return httpx.AsyncClient(transport=transport, **kwargs)

    def client_factory(*args, **kwargs):
        return AuthenticatedApiClient(
            *args,
            **kwargs,
            _oidc_client_factory=http_factory,
            _rest_client_factory=http_factory,
        )

    monkeypatch.setattr(client_module, "AuthenticatedApiClient", client_factory)
    return requests, responses


def outputs(path):
    return dict(line.split("=", 1) for line in path.read_text().splitlines())


@pytest.mark.parametrize("operation", ["submit", "submit-and-wait"])
@pytest.mark.parametrize("source", ["inline", "relative-file", "absolute-file"])
async def test_submit_pins_revision_and_maps_parameters(
    environment, sdk_server, monkeypatch, tmp_path, operation, source
):
    requests, responses = sdk_server
    responses.extend(
        [(200, {"id": 7, "message": "created"}), (200, {"task_id": 42, "message": "ok"})]
    )
    config = {
        "budget": "test-budget",
        "name": "Custom Scout task",
        "parameters": {
            "input_limit": ["src/", "contracts/Vault.sol"],
            "extra_context": 'Check "withdrawals".\nTreat balances carefully. $(not-a-command)',
            "generate_pocs": True,
        },
    }
    if source == "inline":
        monkeypatch.setenv("AH_SCOUT_CONFIG", json.dumps(config))
    else:
        workspace = tmp_path / "consumer checkout"
        workspace.mkdir()
        config_file = workspace / "scout config.json"
        config_file.write_text(json.dumps(config), encoding="utf-8")
        monkeypatch.setenv("GITHUB_WORKSPACE", str(workspace))
        monkeypatch.delenv("AH_SCOUT_CONFIG")
        monkeypatch.setenv(
            "AH_SCOUT_CONFIG_FILE",
            config_file.name if source == "relative-file" else str(config_file),
        )
        # The launcher runs Python from the action's source, not the consumer's checkout.
        action_source = tmp_path / "action source"
        action_source.mkdir()
        monkeypatch.chdir(action_source)
    monkeypatch.setenv("AH_INCLUDES_SUBMODULES", "true")
    if operation == "submit-and-wait":
        responses.append((200, task_response()))
    await run(operation)
    api_requests = [r for r in requests if r.url.host == "app.audithub.dev"]
    assert len(api_requests) == (2 if operation == "submit" else 3)
    version, task = api_requests[:2]
    assert version.url.path == "/api/v1/organizations/1/projects/2/versions-url"
    fields = parse_qs(version.content.decode())
    assert fields["revision"] == fields["commit_hash"] == [SHA]
    assert fields["input_type"] == ["git"]
    assert fields["url"] == ["https://github.com/example/contracts.git"]
    assert fields["includes_submodules"] == ["true"]
    assert task.url.path == "/api/v1/organizations/1/projects/2/versions/7/tools/agent"
    body = json.loads(task.content)
    assert body == config
    expected = {
        "task-id": "42",
        "task-url": "https://app.audithub.dev/app/organizations/1/projects/2/tasks/42/analysis",
    }
    if operation == "submit-and-wait":
        expected |= {
            "findings-count": "0",
            "findings-by-severity": (
                '{"critical":0,"high":0,"medium":0,"low":0,"warning":0,"info":0}'
            ),
        }
    assert outputs(environment) == expected


async def test_minimal_config_uses_defaults(environment, sdk_server):
    requests, responses = sdk_server
    responses.extend(
        [(200, {"id": 7, "message": "created"}), (200, {"task_id": 42, "message": "ok"})]
    )
    await run("submit")
    assert json.loads(requests[-1].content) == {
        "budget": "test-budget",
        "name": f"Scout {SHA[:12]}",
        "parameters": {"generate_pocs": False},
    }


@pytest.mark.parametrize(
    "config",
    [
        "{",
        "",
        "[]",
        "null",
        '"text"',
        "{}",
        '{"budget": " "}',
        '{"budget": 123}',
        '{"budget": "test-budget", "name": 123}',
        '{"budget": "test-budget", "typo": true}',
        '{"budget": "test-budget", "parameters": null}',
        '{"budget": "test-budget", "parameters": []}',
        '{"budget": "test-budget", "parameters": {"generate_poc": true}}',
        '{"budget": "test-budget", "parameters": {"generate_pocs": "true"}}',
        '{"budget": "test-budget", "parameters": {"input_limit": "src/"}}',
        '{"budget": "test-budget", "parameters": {"input_limit": [1]}}',
        '{"budget": "test-budget", "parameters": {"extra_context": 123}}',
        '{"budget": "first", "budget": "second"}',
        '{"budget": "test-budget", "parameters": {"generate_pocs": true, "generate_pocs": false}}',
        '{"budget": "test-budget", "parameters": {"extra_context": NaN}}',
    ],
)
async def test_invalid_config_fails_before_network(environment, sdk_server, monkeypatch, config):
    requests, _ = sdk_server
    monkeypatch.setenv("AH_SCOUT_CONFIG", config)
    with pytest.raises(ValueError):
        await run("submit-and-wait")
    assert not requests
    assert not environment.exists()


async def test_config_sources_are_mutually_exclusive(environment, sdk_server, monkeypatch):
    requests, _ = sdk_server
    monkeypatch.setenv("AH_SCOUT_CONFIG_FILE", "scout.json")
    with pytest.raises(ValueError, match="exactly one"):
        await run("submit")
    assert not requests


@pytest.mark.parametrize("file_state", ["missing", "directory", "invalid-utf8", "invalid-json"])
async def test_invalid_config_file_fails_before_network(
    environment, sdk_server, monkeypatch, tmp_path, file_state
):
    requests, _ = sdk_server
    config_file = tmp_path / "scout.json"
    if file_state == "directory":
        config_file.mkdir()
    elif file_state == "invalid-utf8":
        config_file.write_bytes(b"\xff")
    elif file_state == "invalid-json":
        config_file.write_text("{")
    monkeypatch.delenv("AH_SCOUT_CONFIG")
    monkeypatch.setenv("AH_SCOUT_CONFIG_FILE", str(config_file))
    with pytest.raises(ValueError):
        await run("submit-and-wait")
    assert not requests


def test_config_validation_does_not_log_values(environment, sdk_server, monkeypatch, capsys):
    monkeypatch.setenv(
        "AH_SCOUT_CONFIG",
        '{"budget": "test-budget", "parameters": {"generate_pocs": "sensitive-data-do-not-log"}}',
    )
    monkeypatch.setattr("sys.argv", ["scout", "submit"])
    assert main() == 1
    output = capsys.readouterr().out
    assert "parameters.generate_pocs" in output
    assert "sensitive-data" not in output
    assert not sdk_server[0]


async def test_wait_polls_and_reports_all_severities(environment, sdk_server, monkeypatch):
    requests, responses = sdk_server
    responses.extend(
        [
            (200, task_response("Queued")),
            (200, task_response("Running")),
            (200, task_response(counts={"critical": 1, "high": 2, "info": 3})),
        ]
    )
    sleeps = []

    async def sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", sleep)
    await run("wait")
    assert sleeps == [1, 1]
    assert all(r.method == "GET" for r in requests if r.url.host == "app.audithub.dev")
    result = outputs(environment)
    assert result["findings-count"] == "6"
    assert json.loads(result["findings-by-severity"]) == {
        "critical": 1,
        "high": 2,
        "medium": 0,
        "low": 0,
        "warning": 0,
        "info": 3,
    }


async def test_combined_returns_union_and_zero_findings(environment, sdk_server):
    _, responses = sdk_server
    responses.extend(
        [
            (200, {"id": 7, "message": "created"}),
            (200, {"task_id": 42, "message": "ok"}),
            (200, task_response()),
        ]
    )
    await run("submit-and-wait")
    result = outputs(environment)
    assert set(result) == {"task-id", "task-url", "findings-count", "findings-by-severity"}
    assert result["findings-count"] == "0"
    assert len(json.loads(result["findings-by-severity"])) == 6


@pytest.mark.parametrize(
    "status", ["Failed", "Error", "Canceled", "Finished", "Skipped", "Omitted"]
)
async def test_unsuccessful_terminal_states_fail(environment, sdk_server, status):
    _, responses = sdk_server
    responses.append((200, task_response(status)))
    with pytest.raises(TaskFailed, match=status):
        await run("wait")
    assert not environment.exists()


async def test_combined_keeps_task_outputs_on_failure(environment, sdk_server):
    _, responses = sdk_server
    responses.extend(
        [
            (200, {"id": 7, "message": "created"}),
            (200, {"task_id": 42, "message": "ok"}),
            (200, task_response("Failed")),
        ]
    )
    with pytest.raises(TaskFailed):
        await run("submit-and-wait")
    assert set(outputs(environment)) == {"task-id", "task-url"}


async def test_deadline_includes_poll_sleep(environment, sdk_server, monkeypatch):
    requests, responses = sdk_server
    monkeypatch.setenv("AH_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("AH_POLL_INTERVAL_SECONDS", "300")
    responses.append((200, task_response("Running")))
    with pytest.raises(TimeoutError, match="remote task was not canceled"):
        await asyncio.wait_for(run("wait"), timeout=2)
    assert not environment.exists()
    assert not any(r.method == "DELETE" for r in requests)


async def test_deadline_interrupts_inflight_request(environment, sdk_server, monkeypatch):
    from audithub_sdk import TasksApi

    monkeypatch.setenv("AH_TIMEOUT_SECONDS", "1")

    async def slow_request(*args, **kwargs):
        await asyncio.sleep(300)

    monkeypatch.setattr(
        TasksApi, "get_info_organizations_organization_id_tasks_task_id_get", slow_request
    )
    with pytest.raises(TimeoutError, match="Timed out after 1 seconds"):
        await asyncio.wait_for(run("wait"), timeout=2)


@pytest.mark.parametrize(
    "failure",
    [
        (429, {}),
        (503, {}),
        httpx.ConnectError("mock connection failure"),
    ],
)
async def test_transient_poll_errors_retry(environment, sdk_server, monkeypatch, failure):
    _, responses = sdk_server
    responses.extend([failure, (200, task_response())])

    async def no_sleep(seconds):
        pass

    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    await run("wait")
    assert outputs(environment)["findings-count"] == "0"
    assert not responses


async def test_sdk_refreshes_expired_token(environment, sdk_server):
    requests, responses = sdk_server
    responses.extend([(401, {}), (200, task_response())])
    await run("wait")
    token_requests = [r for r in requests if r.url.path.endswith("/token")]
    assert len(token_requests) == 2


@pytest.mark.parametrize("counts", [None, {"high": -1}, {"unrecognized": 3}])
async def test_missing_or_invalid_counts_never_report_clean_scan(environment, sdk_server, counts):
    _, responses = sdk_server
    response = task_response()
    response["findings_counters"] = counts
    responses.append((200, response))
    with pytest.raises(ValueError):
        await run("wait")
    assert not environment.exists()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("COMMIT", "main"),
        ("COMMIT", "a" * 7),
        ("PROJECT_ID", "0"),
        ("INCLUDES_SUBMODULES", "yes"),
        ("TIMEOUT_SECONDS", "0"),
        ("POLL_INTERVAL_SECONDS", "-1"),
        ("REPOSITORY_URL", "https://token@github.com/a/b"),
        ("CLIENT_SECRET", ""),
    ],
)
async def test_invalid_inputs_fail_before_network(
    environment, sdk_server, monkeypatch, name, value
):
    requests, _ = sdk_server
    monkeypatch.setenv(f"AH_{name}", value)
    with pytest.raises(ValueError):
        await run("submit-and-wait")
    assert not requests


def test_api_errors_are_redacted_and_not_retried(environment, sdk_server, monkeypatch, capsys):
    requests, responses = sdk_server
    responses.append((403, {"detail": "sensitive-data-do-not-log"}))
    monkeypatch.setattr("sys.argv", ["scout", "submit"])
    assert main() == 1
    output = capsys.readouterr().out
    assert "HTTP 403" in output
    assert "sensitive-data" not in output
    assert "test-secret" not in output
    assert len([r for r in requests if r.url.host == "app.audithub.dev"]) == 1


def test_output_newlines_are_rejected(environment):
    with pytest.raises(ValueError, match="Invalid action output"):
        write_outputs({"task-url": "https://app.audithub.dev\nforged-output=true"})
    assert not environment.exists()
