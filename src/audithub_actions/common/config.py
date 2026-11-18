"""Fixed endpoints for the hosted AuditHub service."""

AUDITHUB_BASE_URL = "https://app.audithub.dev/api/v1"
AUDITHUB_OIDC_CONFIGURATION_URL = (
    "https://sso.veridise.com/auth/realms/veridise/.well-known/openid-configuration"
)
AUDITHUB_WEB_URL = AUDITHUB_BASE_URL.removesuffix("/api/v1")
