"""Check the installed distribution from outside a source checkout.

Run with the Python interpreter of a clean environment containing the built
wheel. This check never fetches NASA data or contacts a publishing service.
"""

import json
import os
import subprocess  # nosec B404 - Fixed local Python CLI probes; no shell or external input.
import sys
import tempfile
from importlib.metadata import distribution
from importlib.resources import files
from pathlib import Path

import rulsafe


def _cli(directory: Path, arguments: list[str], expected_status: int = 0) -> str:
    """Run the installed CLI with captured output and a bounded runtime."""
    # Every caller supplies literal CLI arguments to this interpreter; no shell is used.
    completed = subprocess.run(  # noqa: S603  # nosec B603
        [sys.executable, "-m", "rulsafe", *arguments],
        cwd=directory,
        env={**os.environ, "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=120,
        check=False,
        shell=False,
    )
    if completed.returncode != expected_status:
        raise RuntimeError(completed.stdout)
    return completed.stdout


def main() -> None:
    """Validate metadata, resources, CLI execution, and generated reports."""
    source = Path(__file__).resolve().parents[1] / "src"
    if Path(rulsafe.__file__).resolve().is_relative_to(source):
        raise RuntimeError("The distribution check must not import the source checkout.")
    installed = distribution("rulsafe")
    if installed.version != rulsafe.__version__:
        raise RuntimeError("Installed and imported versions differ.")
    metadata = installed.metadata
    if metadata["License-Expression"] != "Apache-2.0":
        raise RuntimeError("SPDX license metadata is missing.")
    if set(metadata.get_all("License-File", [])) != {"LICENSE", "NOTICE"}:
        raise RuntimeError("License and notice metadata must both be present.")
    names = {str(path) for path in installed.files or ()}
    for filename in ("LICENSE", "NOTICE"):
        if not any(name.endswith(f"/licenses/{filename}") for name in names):
            raise RuntimeError(f"Missing packaged {filename}.")
    if any(name.endswith((".csv", ".parquet", ".zip", ".7z", ".mat")) for name in names):
        raise RuntimeError("Dataset-like files must not be in the wheel.")
    resources = files("rulsafe")
    for relative in (
        "py.typed",
        "demo_configs/synthetic_fleet.yaml",
        "demo_configs/cmapss_fd001_completed_trajectory.yaml",
    ):
        if not resources.joinpath(relative).is_file():
            raise RuntimeError(f"Missing package resource {relative}.")
    with tempfile.TemporaryDirectory(prefix="rulsafe-installed-") as temporary:
        directory = Path(temporary)
        output = _cli(directory, ["--version"])
        if output.strip() != f"rulsafe {installed.version}":
            raise RuntimeError("CLI version differs from package metadata.")
        _cli(directory, ["--help"])
        _cli(directory, ["demo", "synthetic"])
        report = directory / "rulsafe-runs/synthetic"
        document = json.loads((report / "report.json").read_text(encoding="utf-8"))
        if document["status"] != "COMPLETED":
            raise RuntimeError("Installed synthetic demo did not complete.")
        if document["censored_or_unsupported_asset_ids"] != ["unit-censored"]:
            raise RuntimeError("Installed demo lost its censored history.")
        metric = document["metrics"]["test"]["hist_gradient_boosting_root_mean_square_error"]
        if metric["status"] != "COMPUTED" or abs(metric["value"] - 1.9655398693652688) > 1e-6:
            raise RuntimeError("Installed demo differs from the measured noisy-fleet reference.")
        if not (report / "report.html").is_file():
            raise RuntimeError("Installed demo did not write its HTML report.")
        missing = _cli(directory, ["demo", "cmapss"], expected_status=2)
        if "data fetch cmapss" not in missing or "Traceback" in missing:
            raise RuntimeError("Missing FD001 data did not give the documented fetch instructions.")
    print(f"Installed rulsafe {installed.version}: metadata, resources, CLI, and reports passed")


if __name__ == "__main__":
    main()
