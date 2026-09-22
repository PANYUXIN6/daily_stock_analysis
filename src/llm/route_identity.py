"""Cloud model route aliases and deployment matching."""
from typing import Any, Dict, List, Sequence


def route_identity_candidates(model: str) -> set[str]:
    """Match bare aliases without changing provider-qualified model identities."""
    text = str(model or "").strip()
    if not text:
        return set()
    candidates = {text}
    if "/" not in text:
        candidates.add(f"deepseek/{text}")
    return candidates


def get_route_deployments(model_list: Sequence[Dict[str, Any]], route_name: str) -> List[Dict[str, Any]]:
    candidates = route_identity_candidates(route_name)
    return [entry for entry in model_list or [] if isinstance(entry, dict)
            and str(entry.get("model_name") or "").strip() in candidates]
