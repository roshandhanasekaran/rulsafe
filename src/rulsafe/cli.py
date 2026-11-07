"""Command-line interface.

``--help`` and ``--version`` work. ``validate`` checks the schema.
``datasets list`` prints access and licence. ``data fetch cmapss`` downloads
the NASA C-MAPSS archive, checks its SHA-256, and writes git-ignored tables.
``demo synthetic`` and ``demo cmapss`` write a JSON report.

Exit codes: 0 success, 1 a check failed, 2 usage or configuration error.
"""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from rulsafe._version import __version__
from rulsafe.api import load_config
from rulsafe.datasets.cards import DatasetCard
from rulsafe.datasets.registry import dataset_card, fetch_dataset, list_datasets
from rulsafe.exceptions import (
    EXIT_CHECK_FAILED,
    EXIT_USAGE_ERROR,
    ConfigurationError,
    ContractError,
    not_implemented,
)

console = Console()
_DEFAULT_INIT_PATH = Path("run.yaml")
_V01_DEMOS = frozenset({"cmapss", "synthetic"})
_SCANIA_DEMO_NAMES = frozenset({"scania", "scania_component_x"})

app = typer.Typer(
    name="rulsafe",
    help=(
        "Completed-trajectory remaining-useful-life research checks. "
        "The v0.1 demo is cmapss. SCANIA fleet data is v0.2. "
        "Not a safety-certified prognostic."
    ),
    no_args_is_help=True,
    add_completion=False,
)
datasets_app = typer.Typer(
    name="datasets",
    help="List reference datasets and fetch C-MAPSS FD001.",
    no_args_is_help=True,
)
data_app = typer.Typer(
    name="data",
    help="Fetch public reference files. Raw archives are not stored in git.",
    no_args_is_help=True,
)
app.add_typer(datasets_app, name="datasets")
app.add_typer(data_app, name="data")


def _print_version(value: bool) -> None:
    """Print the package version and exit when ``--version`` was passed.

    Args:
        value: True when the option is present.

    Raises:
        typer.Exit: After printing the version.
    """
    if not value:
        return
    typer.echo(f"rulsafe {__version__}")
    raise typer.Exit()


def _exit_not_implemented(feature_name: str, *arguments: object) -> None:
    """Print a not-implemented error and exit with a usage code.

    Args:
        feature_name: Public name of the missing command.
        arguments: Arguments the command accepted.

    Raises:
        typer.Exit: Always, with code 2.
    """
    console.print(str(not_implemented(feature_name, *arguments)))
    raise typer.Exit(code=EXIT_USAGE_ERROR)


def _print_card(card: DatasetCard) -> None:
    """Print access and licence as separate lines.

    Args:
        card: Dataset card to show.
    """
    console.print(f"[bold]{card.name}[/bold] (v{card.available_in})")
    console.print(f"Access: {card.access}")
    console.print(card.licence_statement)
    if card.separate_record_note is not None:
        console.print(f"Separate record: {card.separate_record_note}")
    if card.terms is not None:
        console.print(f"Terms: {card.terms}")
    console.print(f"Citation: {card.citation}")
    if card.signal_column_count is not None:
        console.print(f"Signal columns: {card.signal_column_count}")
    console.print("")


@app.callback()
def application(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Show the package version and exit.",
            callback=_print_version,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Completed-trajectory remaining-useful-life research checks for v0.1."""
    if version:
        _print_version(True)


@app.command("init")
def init_command(
    output: Annotated[
        Path,
        typer.Option("--output", help="Where to write the starter YAML."),
    ] = _DEFAULT_INIT_PATH,
) -> None:
    """Write a starter YAML file. Not implemented yet."""
    _exit_not_implemented("init", output)


@app.command("validate")
def validate_command(
    config: Annotated[
        Path,
        typer.Option("--config", help="Path to the YAML run configuration."),
    ],
) -> None:
    """Validate a YAML configuration against the v0.1 schema.

    Referenced data files are not opened.
    """
    try:
        loaded = load_config(config)
    except ConfigurationError as error:
        console.print(f"Invalid configuration: {error}")
        raise typer.Exit(code=EXIT_USAGE_ERROR) from error
    console.print(
        f"Valid configuration for {loaded.project.name} "
        f"({loaded.labeling.task.value}, {loaded.split.protocol.value})."
    )


@app.command("profile")
def profile_command(
    config: Annotated[Path, typer.Option("--config", help="Path to the YAML configuration.")],
) -> None:
    """Summarize row counts and history dispositions. Not implemented yet."""
    _exit_not_implemented("profile", config)


@app.command("check")
def check_command(
    config: Annotated[Path, typer.Option("--config", help="Path to the YAML configuration.")],
) -> None:
    """Run the leakage audit and write a report. Not implemented yet."""
    _exit_not_implemented("check", config)


@app.command("train")
def train_command(
    config: Annotated[Path, typer.Option("--config", help="Path to the YAML configuration.")],
) -> None:
    """Fit the constant and tree baselines and write a report. Not implemented yet."""
    _exit_not_implemented("train", config)


@app.command("report")
def report_command(
    run: Annotated[Path, typer.Option("--run", help="Path of a completed run directory.")],
) -> None:
    """Reprint a saved report. Not implemented yet."""
    _exit_not_implemented("report", run)


@app.command("demo")
def demo_command(
    fixture_name: Annotated[
        str,
        typer.Argument(help="Demo name. Use cmapss for the v0.1 FD001 demo."),
    ],
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Directory for the report."),
    ] = None,
) -> None:
    """Run a demo.

    ``synthetic`` fits the constant and tree baselines on the noisy fleet.
    ``cmapss`` does the same for FD001 after ``rulsafe data fetch cmapss``
    has written the git-ignored tables. The demo does not download by itself.
    """
    normalized = fixture_name.strip().casefold()
    if normalized in _SCANIA_DEMO_NAMES:
        console.print(
            "SCANIA Component X is a v0.2 fleet dataset. The v0.1 demo is: rulsafe demo cmapss"
        )
        raise typer.Exit(code=EXIT_USAGE_ERROR)
    if normalized not in _V01_DEMOS:
        console.print("Unknown demo. Choose cmapss or synthetic.")
        raise typer.Exit(code=EXIT_USAGE_ERROR)
    if normalized == "cmapss":
        _require_cmapss_tables()
    from rulsafe.api import run_pipeline

    config_name = (
        "cmapss_fd001_completed_trajectory.yaml"
        if normalized == "cmapss"
        else "synthetic_fleet.yaml"
    )
    destination = output if output is not None else Path("rulsafe-runs") / normalized
    try:
        config = load_config(Path("examples") / config_name)
        result = run_pipeline(config, output_directory=destination)
    except ContractError as error:
        console.print(str(error))
        raise typer.Exit(code=EXIT_CHECK_FAILED) from error
    except (ConfigurationError, OSError) as error:
        console.print(str(error))
        raise typer.Exit(code=EXIT_USAGE_ERROR) from error
    console.print(f"Wrote {result.report_paths.json_path}")
    console.print(f"Leakage status: {result.leakage.worst_status.value}")


@datasets_app.command("list")
def list_datasets_command() -> None:
    """List reference datasets with access and licence stated separately."""
    for card in list_datasets():
        _print_card(card)


@datasets_app.command("fetch")
def fetch_dataset_command(
    dataset_name: Annotated[
        str,
        typer.Argument(help="Dataset name, for example cmapss_fd001."),
    ],
) -> None:
    """Print access and licence, then download C-MAPSS FD001 when it is v0.1."""
    try:
        card = dataset_card(dataset_name)
    except ConfigurationError as error:
        console.print(str(error))
        raise typer.Exit(code=EXIT_USAGE_ERROR) from error
    _print_card(card)
    try:
        fetch_dataset(dataset_name)
    except ConfigurationError as error:
        console.print(str(error))
        raise typer.Exit(code=EXIT_USAGE_ERROR) from error
    except NotImplementedError as error:
        console.print(str(error))
        raise typer.Exit(code=EXIT_USAGE_ERROR) from error


@data_app.command("fetch")
def data_fetch_command(
    dataset_name: Annotated[
        str,
        typer.Argument(help="Dataset to fetch. Use cmapss."),
    ],
    output: Annotated[
        Path,
        typer.Option("--output", help="Directory for the converted FD001 tables."),
    ] = Path("data/cmapss"),
    from_file: Annotated[
        Path | None,
        typer.Option(
            "--from-file",
            help="Local outer Prognostics zip or inner CMAPSSData.zip. Skips the download.",
        ),
    ] = None,
) -> None:
    """Download NASA C-MAPSS, verify both pinned SHA-256 values, and write FD001.

    The raw zip is not written into the repository. Test engines are stored
    as censored histories and are not given the RUL file as a label.
    ``--from-file`` checks the same pins and does not use the network.
    """
    normalized = dataset_name.strip().casefold()
    if normalized not in {"cmapss", "cmapss_fd001"}:
        console.print("Unknown dataset. Use cmapss.")
        raise typer.Exit(code=EXIT_USAGE_ERROR)
    from rulsafe.datasets.cmapss_convert import CMAPSS_ARCHIVE_URL, fetch_cmapss_fd001

    console.print(f"Source: {from_file if from_file is not None else CMAPSS_ARCHIVE_URL}")
    console.print("Licence: not specified on the NASA catalog page.")
    try:
        written = fetch_cmapss_fd001(output, archive=from_file)
    except ConfigurationError as error:
        console.print(str(error))
        raise typer.Exit(code=EXIT_USAGE_ERROR) from error
    console.print(f"Wrote FD001 tables to {written}")
    console.print(
        "Completed training engines are partitioned in unit-number order. "
        "NASA test engines are censored and excluded. RUL_FD001.txt was not used as a label."
    )


def _require_cmapss_tables() -> None:
    """Stop the C-MAPSS demo when the converted FD001 files are not on disk.

    Raises:
        typer.Exit: When a required file is missing, with code 2.
    """
    config = load_config(Path("examples") / "cmapss_fd001_completed_trajectory.yaml")
    paths = [config.connector.assets, config.connector.signals, config.connector.events]
    partitions = config.split.official_partitions
    if partitions is not None:
        paths.extend([partitions.train_ids, partitions.validation_ids, partitions.test_ids])
    missing = [path.as_posix() for path in paths if not path.is_file()]
    if not missing:
        return
    console.print(
        "C-MAPSS FD001 tables are not on disk. They are not stored in git. "
        "Run `rulsafe data fetch cmapss` from the repository root. "
        "That downloads the NASA Prognostics outer zip "
        "https://phm-datasets.s3.amazonaws.com/NASA/"
        "6.+Turbofan+Engine+Degradation+Simulation+Data+Set.zip , "
        "checks the outer and inner SHA-256 pins, and writes data/cmapss/. "
        "Use --from-file for a local copy. "
        "The NASA catalog licence is not specified. "
        "Without those files the histogram gradient boosting metrics "
        "for this demo are not computed."
    )
    console.print("Missing: " + ", ".join(missing))
    raise typer.Exit(code=EXIT_USAGE_ERROR)


def main() -> None:
    """Run the command-line interface."""
    app()
