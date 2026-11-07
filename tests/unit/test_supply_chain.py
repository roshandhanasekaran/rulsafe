"""Guards for the hashed locks and the supply-chain decision."""

import re
from pathlib import Path

_PYTHON_VERSIONS = ("3.10", "3.11", "3.12", "3.13")


def _lock_text(repository_root: Path, version: str) -> str:
    return (repository_root / "requirements" / f"dev-{version}.lock").read_text(encoding="utf-8")


def _pin(text: str, name: str) -> str:
    for line in text.splitlines():
        if line.startswith(f"{name}=="):
            return line.split(" ", maxsplit=1)[0]
    raise AssertionError(f"{name} is not pinned")


def test_each_python_lock_is_hashed(repository_root: Path) -> None:
    """Every supported interpreter has a hashed lock resolved for that version."""
    for version in _PYTHON_VERSIONS:
        text = _lock_text(repository_root, version)
        assert f"--python-version {version}" in text
        assert "--generate-hashes" in text
        assert _pin(text, "hatchling") == "hatchling==1.33.0"
        assert _pin(text, "editables") == "editables==0.6"
        assert text.count("--hash=sha256:") >= text.count("==")


def test_filelock_pin_installs_on_that_python(repository_root: Path) -> None:
    """Python 3.10 gets a filelock it can install. Newer locks get the patched pin."""
    assert _pin(_lock_text(repository_root, "3.10"), "filelock") == "filelock==4.1.0"
    for version in ("3.11", "3.12", "3.13"):
        assert _pin(_lock_text(repository_root, version), "filelock") == "filelock==4.2.9"


def test_hatchling_build_backend_is_pinned(repository_root: Path) -> None:
    """The build backend is an exact pin, matching the locks."""
    text = (repository_root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'requires = ["hatchling==1.33.0"]' in text


def test_ci_installs_the_lock_for_the_interpreter(repository_root: Path) -> None:
    """CI installs the hashed lock for the job's Python and audits that file."""
    workflow = (repository_root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert 'python-version: ["3.10", "3.11", "3.12", "3.13"]' in workflow
    assert "--require-hashes --only-binary=:all:" in workflow
    assert "requirements/dev-${{ matrix.python-version }}.lock" in workflow
    assert "requirements/dev-3.12.lock" in workflow
    assert 'pip install -e ".[dev]"' not in workflow
    assert "requirements/filelock-unfixed-on-3.10.txt" in workflow
    assert "--log-opts=--all" in workflow
    assert "scripts/install-gitleaks.sh" in workflow


def test_python_310_filelock_ignores_are_explicit(repository_root: Path) -> None:
    """The 3.10 exception names the advisories and does not apply itself to other locks."""
    text = (repository_root / "requirements" / "filelock-unfixed-on-3.10.txt").read_text(
        encoding="utf-8"
    )
    assert "Python >=3.11" in text
    assert "dev-3.10.lock" in text
    identifiers = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert identifiers
    assert all(identifier.startswith("CVE-") for identifier in identifiers)


def test_security_decision_is_proposed_or_accepted(repository_root: Path) -> None:
    """Spike SP-010 is recorded. Accepting it later must not fail this test."""
    text = (repository_root / "docs" / "decisions" / "ADR-010-security-supply-chain.md").read_text(
        encoding="utf-8"
    )
    assert "SP-010" in text
    assert re.search(r"\*\*Status:\*\* (?:Proposed|Accepted)\b", text)
    assert "pip-audit" in text
    assert "gitleaks" in text
    assert "CycloneDX" in text
    assert "trusted publishing" in text
    assert "dev-3.10.lock" in text
