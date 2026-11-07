"""Public Python API.

``load_config`` validates a YAML file. ``run_pipeline`` runs the CSV
group-holdout slice and writes ``report.json``. Checks that did not run
stay ``NOT_CHECKED``.
"""

import json
from collections.abc import Mapping
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
        document: Mapping[str, object] | None = None,
    ) -> None:
        """Store the objects a finished run will expose.

        Args:
            leakage: Leakage audit.
            metrics: Scores by split.
            report_paths: Written report files.
            document: JSON report body, when the run wrote one.
        """
        self.leakage = leakage
        self.metrics = metrics
        self.report_paths = report_paths
        self._document = document

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
            NotImplementedError: This result was not produced by a run.
        """
        if self._document is None:
            raise not_implemented("RunResult.save_json", path)
        destination = Path(path)
        destination.write_text(json.dumps(self._document, indent=2) + "\n", encoding="utf-8")
        return destination

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready mapping of the run.

        Returns:
            Report fields, including leakage coverage.

        Raises:
            NotImplementedError: This result was not produced by a run.
        """
        if self._document is None:
            raise not_implemented("RunResult.to_dict")
        return dict(self._document)

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
    """Run the implemented completed-trajectory check.

    Group holdout on CSV files is implemented. The constant baseline and the
    histogram gradient boosting baseline are fit on training rows only. Early
    stopping uses the validation split. ``censored_policy`` ``report`` keeps
    censored histories in the JSON report and out of every split. ``reject``
    writes a partial report with status ``FAILED`` and no metrics, then raises.
    Official partitions and the C-MAPSS demo need offline files that this
    package does not download.

    Args:
        config: Validated run configuration.
        output_directory: Directory for the run artefacts. The configuration
            report directory is used when this is None.

    Returns:
        The run result, including the JSON report path.

    Raises:
        ConfigurationError: The files or protocol are outside this slice.
        ContractError: ``censored_policy`` is ``reject`` and a censored or
            unsupported history is present. The partial report is written
            before this exception, or the training split has no target.
    """
    from rulsafe.pipeline.execute import execute_group_holdout

    destination = (
        output_directory if output_directory is not None else Path(config.report.output_dir)
    )
    leakage, metrics, document = execute_group_holdout(config, destination)
    report_path = destination / "report.json"
    return RunResult(
        leakage=leakage,
        metrics=metrics,
        report_paths=ReportPaths(html_path=None, json_path=report_path),
        document=document,
    )
