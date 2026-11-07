# ADR-010: Security supply chain

- **Status:** Proposed
- **Date:** 7 November 2026 (Europe/London)
- **Spike:** SP-010

## Context

RULSafe is an Apache-2.0 Python package. v0.1 is not published to PyPI. The repository already runs Ruff, mypy, pytest, Bandit, a gitleaks pre-commit hook, and `pip-audit` against the hashed development locks.

The lock used to pin versions and leave hashes off. Continuous integration then installed with `pip install -e ".[dev]"`, so the job could resolve a different set from the file `pip-audit` read. `pip-audit --disable-pip` also required `--no-deps` until every requirement had a hash.

This spike compares six controls and recommends one posture. The status stays **Proposed** because two of the six (an SBOM artefact and PyPI trusted publishing) are deliberately not wired up while the package is unpublished.

Checked on 7 November 2026 while writing this record:

- `pip-audit` 2.10.1 accepts `--requirement`, `--disable-pip`, `--require-hashes`, and output formats `columns`, `json`, `cyclonedx-json`, `cyclonedx-xml`, and `markdown`.
- `uv pip compile --python-version 3.10 --generate-hashes` writes a fully pinned file. One file per supported interpreter is required, because the patched `filelock` releases do not install on Python 3.10.
- PyPI JSON for `filelock` 4.2.1 through 4.2.9 reports `requires_python >=3.11`. An OSV query for PyPI `filelock` shows the current advisory fixes landing in 4.2.1.
- The Python Packaging User Guide's GitHub Actions publishing page describes PyPI trusted publishing, a pending publisher, a separate build job, `permissions: id-token: write`, the `pypi` GitHub Environment, and `pypa/gh-action-pypi-publish`. From action v1.11.0 that action uploads [PEP 740](https://peps.python.org/pep-0740/) attestations by default.

## Options

### 1. pip-audit against a lockfile

Audit `requirements/dev-3.10.lock` through `requirements/dev-3.13.lock`, and nothing else on the machine. `--disable-pip` keeps the audit on the file the repository committed. With hashes present, `--require-hashes` checks that every pin has a hash, and `--no-deps` is no longer required for `--disable-pip`.

Auditing a live virtualenv answers a different question (what this laptop happened to install). The release gate is the lock.

### 2. Hashed locks

`pip-compile --generate-hashes` records a sha256 for every published artefact of each pinned version. CI installs with:

```bash
python -m pip install --require-hashes --only-binary=:all: -r requirements/dev-3.12.lock
python -m pip install --no-deps --no-build-isolation -e .
```

The lock filename matches the interpreter (`dev-3.10.lock`, `dev-3.11.lock`, `dev-3.12.lock`, `dev-3.13.lock`). Each file is produced with `uv pip compile --python-version <that version> --generate-hashes`.

`--require-hashes` rejects a missing or mismatched hash. `--only-binary=:all:` refuses an sdist, so a package cannot run `setup.py` as a substitute for the wheel whose hash is in the lock. `--no-build-isolation` builds the editable install with `hatchling` from that same lock. `hatchling` is listed in the `dev` extra so the lock contains the build backend and its dependencies.

`pip` itself stays out of the lock. pip-compile treats it as unsafe to pin there. CI may upgrade `pip` before the hashed install. That one tool is the remaining unpinned installer.

Hashes are collected from PyPI when the lock is generated. Review of the lock diff is the point where a substituted artefact has to be accepted. Later CI installs do not trust a new upload of the same version.

### 3. Bandit

Bandit scans this repository's Python. It does not audit third-party wheels. The running configuration skips B101 (assert) and scans `src/`. B105 is not a global skip. The leakage status `PASS` carries a targeted `# nosec B105` because the name matches Bandit's hardcoded-password rule.

CI calls `bandit -c .bandit -r src`. The pre-commit hook uses the same config file.

### 4. Gitleaks

Gitleaks scans git content for secrets. The pre-commit hook sees what is being committed. It does not see a secret that was committed earlier and deleted. CI checks out the full history (`fetch-depth: 0`) and runs:

```bash
gitleaks detect --source . --log-opts=--all --redact --verbose --no-banner
```

The binary is gitleaks 8.30.1, the same revision as `.pre-commit-config.yaml`. `scripts/install-gitleaks.sh` checks the published sha256 before installing it. Tests call that binary. They do not download it.

### 5. SBOM

`pip-audit --format cyclonedx-json` writes a CycloneDX BOM from the same requirement file it audits. `cyclonedx-xml` is the other format that this installed `pip-audit` offers. No second scanner is required.

The useful BOM is an artefact of a release, produced from the lock for the interpreter that built the wheel. Committing a generated BOM next to the lock creates a second file that can drift. The proposal is to upload `cyclonedx-json` from the release workflow when that workflow exists, and to keep vulnerability gating on the `pip-audit` exit code.

### 6. PyPI trusted publishing

The Packaging User Guide's current GitHub Actions flow is:

1. Build the sdist and wheel in one job and upload them as a workflow artefact.
2. Publish from a later job that only downloads those files.
3. Register a pending publisher at `https://pypi.org/manage/account/publishing/` for the project name, the GitHub repository, the workflow filename, and the GitHub Environment name `pypi`.
4. Grant that publish job `id-token: write` and require manual approval on the `pypi` environment.
5. Upload with `pypa/gh-action-pypi-publish@release/v1`, which obtains a short-lived token through GitHub's OpenID Connect provider and attaches PEP 740 attestations.

A long-lived `PYPI_API_TOKEN` is the older path. This record does not add one. Publishing stays out of the repository until v0.1 is stable, which is the existing product rule. The workflow file is not added in this change.

## Recommendation

Use all six, in this order of enforcement:

1. One hashed lock per supported interpreter, `requirements/dev-3.10.lock` through `requirements/dev-3.13.lock`, each from `uv pip compile --python-version <version> --generate-hashes --extra dev --extra demo`.
2. Every CI install uses the lock for that job's Python, with `--require-hashes` and `--only-binary=:all:`.
3. `pip-audit --requirement requirements/dev-<version>.lock --disable-pip --require-hashes` is the vulnerability gate for that interpreter.
4. Bandit stays on `src/` with `.bandit`.
5. Gitleaks 8.30.1 scans the full history in CI, and the pre-commit hook stays as the commit-time check.
6. When a release exists, emit a CycloneDX JSON BOM from the lock that built the wheel and publish through PyPI trusted publishing. Do not commit the BOM. Do not store a PyPI API token.

`[build-system] requires` pins `hatchling==1.33.0`. The same pin is in every lock, with `editables==0.6`, so `pip install --no-deps --no-build-isolation -e .` uses that backend.

`filelock` is the split. Releases that fix the current advisories, starting at 4.2.1, declare `requires_python >=3.11`. `virtualenv` (via pre-commit) and `CacheControl[filecache]` (via pip-audit) both depend on it. The 3.10 lock therefore pins `filelock==4.1.0`, which installs. The 3.11, 3.12, and 3.13 locks pin `filelock==4.2.9`. Audits of those three locks must pass with no ignored advisories. The 3.10 audit ignores only the identifiers in `requirements/filelock-unfixed-on-3.10.txt`, which are the advisories whose fix is 4.2.1. A new advisory, or `filelock==4.1.0` showing up in a newer lock, still fails the gate.

## What is already in the tree

- `requirements/dev-3.10.lock` through `requirements/dev-3.13.lock` are hashed, and CI installs the file that matches the job's Python with `--require-hashes`.
- `pip-audit` reads that same file with `--disable-pip --require-hashes`. The 3.10 job ignores only the filelock advisories listed in `requirements/filelock-unfixed-on-3.10.txt`.
- Bandit uses `.bandit`.
- The security workflow runs gitleaks over `--log-opts=--all`.
- Tests call the local `ruff`, `mypy`, `bandit`, and `gitleaks` binaries on a planted violation. A test that needs a download uses the `network` marker and stays out of the default run.

## Still proposed

- A release job that writes a CycloneDX JSON BOM from the lock used to build the wheel and uploads it as an artefact.
- A publish job that uses PyPI trusted publishing, a `pypi` environment with manual approval, and `pypa/gh-action-pypi-publish@release/v1`.
- Accepting this record. It stays **Proposed** until those two release steps exist and a maintainer marks it Accepted.

## Consequences

- Lock diffs get larger because each pin lists many hashes, and there are four files. Regenerate them. Do not edit hashes by hand.
- Contributors install the lock that matches their interpreter. The command is in `CONTRIBUTING.md`.
- `pip` is pinned in these locks because `pip-api` depends on it. The upgrade step in CI only exists so an older installer can read `--require-hashes` before the lock replaces it.
- Python 3.10 development installs include `filelock==4.1.0`. That is a known, documented gap. It is not hidden by resolving the extra without a lock.
- Secret-scanning tests and the full-history scan must keep planted material out of this repository's commits. The tests write it under the pytest temporary directory.
