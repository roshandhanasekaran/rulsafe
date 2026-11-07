# Contributing

RULSafe v0.1 is a completed-trajectory remaining-useful-life toolkit. SCANIA and other censored fleet adapters are v0.2. Please do not add a web application, a warehouse connector, AutoGluon, Chronos, or a persistence baseline.

## Setup

Use Python 3.10 or newer. Continuous integration runs 3.10, 3.11, 3.12, and 3.13.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

Before a pull request:

```bash
pre-commit run --all-files
ruff check .
ruff format --check .
mypy src
pytest
```

## Pull requests

1. Work on a branch. Keep the change focused on one behavior.
2. Fill in `.github/PULL_REQUEST_TEMPLATE.md`: summary, scope, and the checkboxes.
3. Run the commands in Setup before asking for review. `pre-commit run --all-files` is the same set the hooks run on commit.
4. In the pull request, say what a user can do after the change and what is still `NotImplementedError`.
5. Do not add dataset files, secrets, or a silent drop of a history the toolkit cannot score.
6. A reviewer looks for the schema change, a test, and an update to `CHANGELOG.md` when the user-visible contract moves.

Bug reports and feature requests use the templates in `.github/ISSUE_TEMPLATE/`. Security reports stay private; see `SECURITY.md`.

## Style

- Google docstrings on public modules, classes, and functions. Ruff checks them with pydocstyle's Google convention. The summary is one imperative line, then `Args`, `Returns`, and `Raises` as needed:

  ```python
  def load_config(path: str | Path) -> RunConfig:
      """Load a run configuration from a YAML file.

      Args:
          path: Filesystem path of the YAML configuration.

      Returns:
          The validated configuration.

      Raises:
          ConfigurationError: The file is unreadable or fails the schema.
      """
  ```
- Ruff also runs formatting, isort, pep8-naming, pyupgrade, bugbear, simplify, and the bandit-style `S` rules.
- `mypy` is strict on `src/`. The package ships `py.typed`.
- Prefer small functions with full words in Python names (`output_directory`, not `out_dir`). Configuration field names stay as the YAML contract writes them (`output_dir`, `id_column`, `gap_policy: ffill`), because those keys are the file format.
- Do not drop a censored or unsupported history without a finding. The disposition is `reject` or `report`.
- Do not invent dataset licences. C-MAPSS on the NASA catalog is "not specified". The Zenodo CC BY 4.0 statement stays on its own line. SCANIA is CC BY 4.0 and is not re-licensed as Apache-2.0.
- Do not put third-party dataset files, access keys, or secrets in the repository.

## Tests

Schema and command-line tests live in `tests/unit/`. Planted leakage fixtures and the two invariance tests are described under `tests/leakage/` and `tests/invariance/` and are not written yet. Default CI must not download C-MAPSS or SCANIA.

## Reports

A leakage check that did not run is `NOT_CHECKED`, not a pass. Fleet alert metrics are not covered in v0.1; say so in the report instead of omitting the section.
