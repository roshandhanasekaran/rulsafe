"""Rejection of persistence baselines.

On a completed trajectory, remaining time satisfies
``remaining(t) = remaining(t - step) - step`` until any cap. Persisting the
previous remaining time, or subtracting elapsed time from it, copies the
label. A previous-label persist for a horizon classifier is the same kind of
mistake. This module refuses those names before a model is constructed.
"""

from rulsafe.exceptions import ConfigurationError

_PERSISTENCE_MARKER = "persist"


def reject_persistence_baseline(model_name: str) -> str:
    """Return a cleaned model name, or reject a persistence baseline.

    Args:
        model_name: Model name from configuration, before it is matched to the allowlist.

    Returns:
        The stripped model name when it does not select persistence.

    Raises:
        ConfigurationError: The name is a persistence baseline.
    """
    stripped_name = model_name.strip()
    if _PERSISTENCE_MARKER in stripped_name.casefold():
        raise ConfigurationError(
            "Persistence baselines are rejected. Persisting a previous remaining-useful-life "
            "value copies the label, so it is not a baseline."
        )
    return stripped_name
