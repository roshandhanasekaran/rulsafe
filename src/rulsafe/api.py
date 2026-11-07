"""Public Python API.

``load_config`` validates a YAML file. ``run_pipeline`` is the v0.1 entry
point and is not implemented yet. Results will carry an audit whose missing
checks are ``NOT_CHECKED``, never an implied pass.
"""

from pathlib import Path

import yaml

from rulsafe.config import RunConfig
from rulsafe.eval.metrics import MetricsReport
from rulsafe.exceptions import ConfigurationError, not_implemented
from rulsafe.leakage.suite import LeakageSuiteResult


class ReportPaths:
    """Files written for one run.

    Attributes:
        html_path: Self-contained HTML report, when it has been written.
        json_path: Machine-readable report, when it has been written.
    """

    def __init__(self, html_path: Path | None, json_path: Path | None) -> None:
        """Store report paths.

        Args:
            html_path: HTML report path, or None before it is written.
            json_path: JSON report path, or None before it is written.
        """
        self.html_path = html_path
        self.json_path = json_path


class RunResult:
    """Source of truth for one completed-trajectory run.

    Attributes:
        leakage: Audit findings, including documented coverage.
        metrics: Validation metrics and the frozen final-test metrics.
        report_paths: HTML and JSON paths under the run directory.
    """

    def __init__(
        self,
        leakage: LeakageSuiteResult,
        metrics: MetricsReport,
        report_paths: ReportPaths,
    ) -> None:
        """Store the objects a finished run will expose.

        Args:
            leakage: Leakage audit.
            metrics: Scores by split.
            report_paths: Written report files.
        """
        self.leakage = leakage
        self.metrics = metrics
        self.report_paths = report_paths

    def save_html(self, path: str | Path) -> Path:
        """Write a self-contained HTML report.

        Args:
            path: Destination path.

        Returns:
            The path that was written.

        Raises:
            NotImplementedError: HTML reports are not implemented yet.
        """
        raise not_implemented("RunResult.save_html", path)

    def save_json(self, path: str | Path) -> Path:
        """Write the machine-readable report.

        Args:
            path: Destination path.

        Returns:
            The path that was written.

        Raises:
            NotImplementedError: JSON reports are not implemented yet.
        """
        raise not_implemented("RunResult.save_json", path)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready mapping of the run.

        Returns:
            Report fields, including leakage coverage.

        Raises:
            NotImplementedError: Serialization is not implemented yet.
        """
        raise not_implemented("RunResult.to_dict")

    def _repr_html_(self) -> str:
        """Return a compact notebook summary.

        Returns:
            HTML for a notebook display.

        Raises:
            NotImplementedError: Notebook display is not implemented yet.
        """
        raise not_implemented("RunResult._repr_html_")


def load_config(path: str | Path) -> RunConfig:
    """Load a run configuration from a YAML file.

    The file is schema-checked only. Referenced CSV and Parquet paths are
    not opened.

    Args:
        path: Filesystem path of the YAML configuration.

    Returns:
        The validated configuration.

    Raises:
        ConfigurationError: The file cannot be read, is not a mapping, or fails the schema.
    """
    configuration_path = Path(path)
    try:
        text = configuration_path.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigurationError(
            f"Could not read configuration file {configuration_path}."
        ) from error
    try:
        loaded: object = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise ConfigurationError(f"Invalid YAML in {configuration_path}.") from error
    if loaded is None:
        raise ConfigurationError(f"Configuration file {configuration_path} is empty.")
    if not isinstance(loaded, dict):
        raise ConfigurationError("Configuration root must be a mapping.")
    document: dict[str, object] = {}
    for key, value in loaded.items():
        if not isinstance(key, str):
            raise ConfigurationError("Configuration keys must be strings.")
        document[key] = value
    return RunConfig.from_mapping(document)


def run_pipeline(config: RunConfig, output_directory: Path | None = None) -> RunResult:
    """Run the v0.1 completed-trajectory check.

    The later implementation keeps train, validation, and final test apart,
    builds causal windows, fits preprocessing on train only, and writes an
    audit. Censored and unsupported histories are rejected or reported.

    Args:
        config: Validated run configuration.
        output_directory: Directory for the run artefacts. The configuration
            report directory is used when this is None.

    Returns:
        The run result, including report paths.

    Raises:
        NotImplementedError: The pipeline is not implemented yet.
    """
    raise not_implemented("run_pipeline", config, output_directory)
