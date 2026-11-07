"""Errors and process exit codes for RULSafe.

Exit codes match the command-line contract:

* ``0`` means the run finished and no confirmed ``fail_on`` leakage was found.
* ``1`` means a confirmed leakage finding or another failed ``fail_on`` check.
* ``2`` means the invocation, configuration, or local files could not be used.
"""

EXIT_SUCCESS: int = 0
EXIT_CHECK_FAILED: int = 1
EXIT_USAGE_ERROR: int = 2


class RulsafeError(Exception):
    """Base class for errors raised by this package."""


class ConfigurationError(RulsafeError):
    """The run configuration is missing, unreadable, or does not match the schema."""


class ContractError(RulsafeError):
    """A logical table or episode rule broke the data contract."""


class UsageError(RulsafeError):
    """The call or command line does not match the public interface."""


def not_implemented(feature_name: str, /, *arguments: object) -> NotImplementedError:
    """Build the error used by a specified feature that is not built yet.

    Args:
        feature_name: Public name of the feature.
        arguments: Values accepted by the caller. Only the count is recorded.

    Returns:
        The error the caller should raise.
    """
    argument_count = len(arguments)
    return NotImplementedError(
        f"{feature_name} is part of the specification and is not implemented yet "
        f"(received {argument_count} argument(s))."
    )
