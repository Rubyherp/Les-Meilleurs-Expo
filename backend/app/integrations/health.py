"""Sanitised integration health aggregation.

Never makes paid provider calls.  Never exposes URLs that could contain
credentials, hostnames, or environment values.
"""

from app.core.config import Settings

from app.integrations.models import IntegrationHealth


def get_integration_health(settings: Settings) -> IntegrationHealth:
    """Return configuration state with safe details only.

    The returned ``IntegrationHealth`` communicates whether each provider is
    configured (has a non‑empty key / enabled flag) without revealing secrets.
    """
    providers: dict[str, str] = {}

    # -- OpenAI -----------------------------------------------------------
    providers["openai"] = (
        "configured" if settings.openai_api_key else "not_configured"
    )

    # -- Agnes ------------------------------------------------------------
    providers["agnes"] = (
        "configured" if settings.agnes_api_key else "not_configured"
    )

    # -- Zo ---------------------------------------------------------------
    providers["zo"] = (
        "configured" if settings.zo_api_key else "not_configured"
    )

    # -- GMI Cloud --------------------------------------------------------
    providers["gmi"] = "configured" if (
        settings.gmi_api_key or settings.gmi_enabled
    ) else "not_configured"

    # Determine overall health.
    configured = sum(1 for v in providers.values() if v == "configured")
    total = len(providers)

    if configured == 0:
        overall = "not_configured"
        message = "No providers configured — all integrations are inactive."
    elif configured == total:
        overall = "healthy"
        message = f"All {total} providers configured."
    elif configured >= total // 2:
        overall = "partial"
        message = f"{configured} of {total} providers configured."
    else:
        overall = "degraded"
        message = f"Only {configured} of {total} providers configured."

    return IntegrationHealth(
        overall=overall,
        providers=providers,
        message=message,
    )
