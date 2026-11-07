"""Shared paths for the schema and command-line tests."""

from pathlib import Path

import pytest
import yaml


@pytest.fixture
def repository_root() -> Path:
    """Return the repository root."""
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def load_example(repository_root: Path):
    """Return a loader for example YAML documents."""

    def _load(name: str) -> dict[str, object]:
        loaded = yaml.safe_load((repository_root / "examples" / name).read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise AssertionError(f"{name} is not a mapping")
        document: dict[str, object] = {}
        for key, value in loaded.items():
            if not isinstance(key, str):
                raise AssertionError("example keys must be strings")
            document[key] = value
        return document

    return _load
