"""Configure the SDK's OIDC client, including its token refresh support."""

from audithub_sdk import Configuration
from audithub_sdk_ext import AuthenticatedApiClient, OIDCClientCredentialsContext

from audithub_actions.common.config import AUDITHUB_BASE_URL, AUDITHUB_OIDC_CONFIGURATION_URL
from audithub_actions.common.inputs import get_input


def create_client() -> AuthenticatedApiClient:
    return AuthenticatedApiClient(
        Configuration(host=AUDITHUB_BASE_URL),
        auth_context=OIDCClientCredentialsContext(
            oidc_configuration_url=AUDITHUB_OIDC_CONFIGURATION_URL,
            client_id=get_input("client-id", required=True),
            client_secret=get_input("client-secret", required=True),
            scope=get_input("oidc-scope", "openid profile") or None,
        ),
    )
