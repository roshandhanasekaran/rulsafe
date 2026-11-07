"""Prove pre-commit hooks catch a planted secret and a lint violation.

The planted files are written in a temporary git repository. They are not
part of this source tree.
"""

import base64
import shutil
import subprocess
from pathlib import Path

import pytest

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _git(repository: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run git with a fixed executable and captured output.

    Args:
        repository: Working directory.
        args: Git arguments. The executable is not taken from user input.

    Returns:
        The completed process.
    """
    # git is a fixed tool name. The arguments are written by this test, not by a user.
    return subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
        shell=False,
    )


def _pre_commit(repository: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run pre-commit with a fixed executable and captured output.

    Args:
        repository: Working directory.
        args: Pre-commit arguments. The executable is not taken from user input.

    Returns:
        The completed process.
    """
    # pre-commit is a fixed tool name. The arguments are written by this test, not by a user.
    return subprocess.run(  # noqa: S603
        ["pre-commit", *args],  # noqa: S607
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
        shell=False,
    )


def _planted_private_key() -> str:
    """Build a fake private-key blob.

    The header is decoded at runtime so this source file does not contain
    the text the private-key hook searches for.

    Returns:
        Text that private-key hooks treat as a key.
    """
    begin = base64.b64decode("LS0tLS1CRUdJTiBSU0EgUFJJVkFURSBLRVktLS0tLQ==").decode()
    end = base64.b64decode("LS0tLS1FTkQgUlNBIFBSSVZBVEUgS0VZLS0tLS0=").decode()
    return f"{begin}\nMIIEowIBAAKCAQEA\n{end}\n"


@pytest.fixture
def planted_repository(tmp_path: Path) -> Path:
    """Create a tiny git repository that uses this project's hook config.

    Args:
        tmp_path: Pytest temporary directory.

    Returns:
        The repository root.
    """
    repository = tmp_path / "planted"
    repository.mkdir()
    init = _git(repository, "init")
    assert init.returncode == 0, init.stderr
    shutil.copy(
        _REPOSITORY_ROOT / ".pre-commit-config.yaml",
        repository / ".pre-commit-config.yaml",
    )
    shutil.copy(_REPOSITORY_ROOT / "pyproject.toml", repository / "pyproject.toml")
    (repository / "secret.txt").write_text(_planted_private_key(), encoding="utf-8")
    (repository / "bad.py").write_text("import os\n", encoding="utf-8")
    added = _git(
        repository,
        "add",
        ".pre-commit-config.yaml",
        "pyproject.toml",
        "secret.txt",
        "bad.py",
    )
    assert added.returncode == 0, added.stderr
    return repository


def test_detect_private_key_hook_catches_a_planted_secret(planted_repository: Path) -> None:
    """The detect-private-key hook fails on a planted key."""
    if shutil.which("pre-commit") is None:
        pytest.skip("pre-commit is not installed")
    result = _pre_commit(
        planted_repository,
        "run",
        "detect-private-key",
        "--files",
        "secret.txt",
    )
    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert "secret.txt" in combined


def test_ruff_hook_catches_a_planted_lint_violation(planted_repository: Path) -> None:
    """The ruff hook fails on a planted unused import."""
    if shutil.which("pre-commit") is None:
        pytest.skip("pre-commit is not installed")
    result = _pre_commit(planted_repository, "run", "ruff", "--files", "bad.py")
    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert "bad.py" in combined
