"""Read cloud Agent availability without making model requests."""
from typing import Any, Dict
from src.config import Config


def evaluate_agent_backend_config(config: Config) -> Dict[str, Any]:
    enabled = not (getattr(config, "_agent_mode_explicit", False) and not getattr(config, "agent_mode", False))
    available = enabled and config.is_agent_available()
    return {
        "backend": "litellm",
        "available": available,
        "experimental": False,
        "version": None,
        "error_code": None if available else ("agent_mode_disabled" if not enabled else "capability_unsupported"),
        "message": None if available else ("Agent mode is disabled" if not enabled else "Cloud Agent model is not configured"),
    }


class AgentBackendStatusService:
    def __init__(self, *, config: Config):
        self.config = config

    def get_status(self) -> Dict[str, Any]:
        return evaluate_agent_backend_config(self.config)
