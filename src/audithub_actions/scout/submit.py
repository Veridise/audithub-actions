"""Create a project version at an exact commit, then submit a Scout task."""

import re
from dataclasses import dataclass
from uuid import uuid4

from audithub_sdk import AgentInput, ToolsApi, VersionsApi

from audithub_actions.common.inputs import boolean, get_input, https_url, positive_integer
from audithub_actions.scout.config import load_config


@dataclass(frozen=True)
class Submission:
    organization_id: int
    project_id: int
    repository_url: str
    commit: str
    version_name: str
    includes_submodules: bool
    agent_input: AgentInput

    @classmethod
    def from_inputs(cls, organization_id: int) -> "Submission":
        commit = get_input("commit", required=True)
        if not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
            raise ValueError("The commit input must be a full 40-character Git commit SHA.")
        commit = commit.lower()
        return cls(
            organization_id=organization_id,
            project_id=positive_integer("project-id"),
            repository_url=https_url("repository-url"),
            commit=commit,
            version_name=get_input("version-name") or f"scout-{commit[:12]}-{uuid4().hex}",
            includes_submodules=boolean("includes-submodules"),
            agent_input=load_config(commit),
        )


async def submit(versions: VersionsApi, tools: ToolsApi, request: Submission) -> int:
    # Set revision as well as metadata: commit_hash alone does not select the code to scan.
    version = await versions.post_version_with_url_organizations_organization_id_projects_project_id_versions_url_post(  # noqa: E501
        organization_id=request.organization_id,
        project_id=request.project_id,
        name=request.version_name,
        input_type="git",
        url=request.repository_url,
        revision=request.commit,
        commit_hash=request.commit,
        includes_submodules=request.includes_submodules,
        _request_timeout=300,
    )
    print(f"Created AuditHub version {version.id} for commit {request.commit}.", flush=True)
    # Do not retry these POSTs: a lost response may still have created the resource.
    task = await tools.post_tool_agent_organizations_organization_id_projects_project_id_versions_version_id_tools_agent_post(  # noqa: E501
        organization_id=request.organization_id,
        project_id=request.project_id,
        version_id=version.id,
        agent_input=request.agent_input,
        _request_timeout=300,
    )
    return task.task_id
