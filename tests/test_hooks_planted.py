"""Prove local scanners reject a planted violation.

The planted files live in a temporary directory. They are not part of this
source tree. Each test calls a tool already installed on PATH. Nothing here
downloads a pre-commit hook repository or a scanner release.

A check that needs a download belongs in a different test marked ``network``.
Default runs skip that marker. Pass ``pytest -m network`` to opt in.
Missing tools fail the test. They are not skipped.
"""

import base64
import shutil
import subprocess
from pathlib import Path

import pytest

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _require_tool(name: str) -> str:
    """Return the absolute path of a local executable.

    Args:
        name: Tool name to resolve on PATH.

    Returns:
        Absolute path of the executable.
    """
    resolved = shutil.which(name)
    if resolved is None:
        pytest.fail(
            f"{name} is not installed on PATH. "
            "This test fails instead of skipping, and it does not download the tool."
        )
    return resolved


def _run(
    executable: str,
    *args: str,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a local executable with captured text output.

    Args:
        executable: Absolute path returned by ``_require_tool`` or ``git``.
        args: Arguments written by this test.
        cwd: Working directory.

    Returns:
        The completed process.
    """
    # The executable path is resolved by this test. The shell is not used.
    return subprocess.run(  # noqa: S603
        [executable, *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        shell=False,
    )


def _git(repository: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run git with a fixed executable and captured output.

    Args:
        repository: Working directory.
        args: Git arguments. The executable is not taken from user input.

    Returns:
        The completed process.
    """
    git = _require_tool("git")
    return _run(git, *args, cwd=repository)


def _planted_private_key() -> str:
    """Build a fake private-key blob long enough for the gitleaks rule.

    The header is decoded at runtime so this source file does not contain
    the text a secret scanner searches for. The body is padding, not a key.

    Returns:
        Text that the default gitleaks private-key rule matches.
    """
    begin = base64.b64decode("LS0tLS1CRUdJTiBSU0EgUFJJVkFURSBLRVktLS0tLQ==").decode()
    end = base64.b64decode("LS0tLS1FTkQgUlNBIFBSSVZBVEUgS0VZLS0tLS0=").decode()
    body = "A" * 80
    return f"{begin}\n{body}\n{end}\n"


def test_ruff_fails_on_a_planted_unused_import(tmp_path: Path) -> None:
    """Ruff reports the planted unused import."""
    ruff = _require_tool("ruff")
    target = tmp_path / "bad.py"
    target.write_text("import os\n", encoding="utf-8")
    result = _run(ruff, "check", "--config", str(_REPOSITORY_ROOT / "pyproject.toml"), str(target))
    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert "F401" in combined


def test_mypy_fails_on_a_planted_type_error(tmp_path: Path) -> None:
    """Mypy reports the planted assignment error."""
    mypy = _require_tool("mypy")
    target = tmp_path / "typed.py"
    target.write_text('value: int = "no"\n', encoding="utf-8")
    result = _run(mypy, "--strict", "--no-error-summary", str(target), cwd=tmp_path)
    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert "error:" in combined


def test_bandit_fails_on_a_planted_shell_call(tmp_path: Path) -> None:
    """Bandit, using this repository's config, reports the planted shell call."""
    bandit = _require_tool("bandit")
    target = tmp_path / "shell_call.py"
    target.write_text(
        "\n".join(
            [
                "import subprocess",
                "",
                "",
                "def run() -> None:",
                "    subprocess.call('echo planted', shell=True)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    result = _run(bandit, "-c", str(_REPOSITORY_ROOT / ".bandit"), str(target))
    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert "B602" in combined


def test_gitleaks_fails_on_a_planted_secret(tmp_path: Path) -> None:
    """Gitleaks reports a secret committed only inside a temporary repository."""
    gitleaks = _require_tool("gitleaks")
    repository = tmp_path / "planted"
    repository.mkdir()
    init = _git(repository, "init")
    assert init.returncode == 0, init.stderr
    email = _git(repository, "config", "user.email", "planted@example.com")
    name = _git(repository, "config", "user.name", "Planted")
    assert email.returncode == 0, email.stderr
    assert name.returncode == 0, name.stderr
    (repository / "secret.txt").write_text(_planted_private_key(), encoding="utf-8")
    added = _git(repository, "add", "secret.txt")
    assert added.returncode == 0, added.stderr
    committed = _git(
        repository,
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-m",
        "plant a key",
    )
    assert committed.returncode == 0, committed.stderr
    result = _run(
        gitleaks,
        "detect",
        "--source",
        str(repository),
        "--log-opts=--all",
        "--redact",
        "--no-banner",
        "--no-color",
    )
    combined = result.stdout + result.stderr
    assert result.returncode == 1
    assert "leaks found" in combined
