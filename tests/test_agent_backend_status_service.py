"""Cloud Chat availability is based on enabled mode and usable model routing."""
from types import SimpleNamespace
import pytest
from src.services.agent_backend_status_service import AgentBackendStatusService


@pytest.mark.parametrize("enabled,configured,available,code", [
    (False, True, False, "agent_mode_disabled"),
    (True, False, False, "capability_unsupported"),
    (True, True, True, None),
])
def test_cloud_agent_status(enabled, configured, available, code):
    config = SimpleNamespace(_agent_mode_explicit=True, agent_mode=enabled, is_agent_available=lambda: configured)
    status = AgentBackendStatusService(config=config).get_status()
    assert status["available"] is available
    assert status["error_code"] == code
    assert status["backend"] == "litellm"
