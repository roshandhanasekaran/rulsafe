"""Command-line interface.

``--help`` and ``--version`` work. ``validate`` checks the schema.
``datasets list`` prints access and licence. Everything that would train,
download, or write a report exits with code 2 until it is implemented.

Exit codes: 0 success, 1 confirmed leakage once checks exist, 2 usage or
configuration error.
"""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from rulsafe._version import __version__
from rulsafe.api import load_config
from rulsafe.datasets.cards import DatasetCard
from rulsafe.datasets.registry import dataset_card, fetch_dataset, list_datasets
from rulsafe.exceptions import EXIT_USAGE_ERROR, ConfigurationError, not_implemented

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
    help="List reference datasets. Downloads are not implemented in this release.",
    no_args_is_help=True,
)
app.add_typer(datasets_app, name="datasets")


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
    """Run a demo. ``cmapss`` uses C-MAPSS FD001 plus the synthetic fixtures."""
    normalized = fixture_name.strip().casefold()
    if normalized in _SCANIA_DEMO_NAMES:
        console.print(
            "SCANIA Component X is a v0.2 fleet dataset. The v0.1 demo is: rulsafe demo cmapss"
        )
        raise typer.Exit(code=EXIT_USAGE_ERROR)
    if normalized not in _V01_DEMOS:
        console.print("Unknown demo. Choose cmapss or synthetic.")
        raise typer.Exit(code=EXIT_USAGE_ERROR)
    _exit_not_implemented("demo", normalized, output)


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
    """Print access and licence, then download. Download is not implemented."""
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


def main() -> None:
    """Run the command-line interface."""
    app()
