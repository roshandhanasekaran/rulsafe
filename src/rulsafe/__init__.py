"""Leakage-safe completed-trajectory remaining-useful-life checks.

RULSafe v0.1 is a research toolkit for one completed-trajectory question.
It prepares causal training rows, keeps train, validation, and final test
apart, and writes an audit whose coverage is explicit. It is not a web
application and it is not a safety-certified prognostic.

Censored fleet data, including SCANIA Component X, is v0.2. v0.1 stops when
``censored_policy`` is ``reject``, and when it is ``report`` names the
history and leaves it out of every split.
"""

from rulsafe._version import __version__ as __version__
from rulsafe.api import RunResult as RunResult
from rulsafe.api import load_config as load_config
from rulsafe.api import run_pipeline as run_pipeline
from rulsafe.config import RunConfig as RunConfig
from rulsafe.exceptions import ConfigurationError as ConfigurationError
from rulsafe.exceptions import RulsafeError as RulsafeError

__all__ = [
    "ConfigurationError",
    "RulsafeError",
    "RunConfig",
    "RunResult",
    "__version__",
    "load_config",
    "run_pipeline",
]
