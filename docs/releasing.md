# Preparing and reviewing v0.1.0

The candidate version is 0.1.0. It is **unreleased**: no tag, GitHub Release,
PyPI/TestPyPI upload, or repository visibility change has been made.
The repository stays private until the owner separately approves going public.
This procedure prepares artifacts; it does not authorize publication.

## Review the changes

The PRs are stacked so each diff stays focused. Review and merge them in order
only after owner review:

1. [Noisy-fleet numerical reference and independent verification](https://github.com/roshandhanasekaran/rulsafe/pull/1).
2. [README, input quickstart, and v0.1.0 changelog](https://github.com/roshandhanasekaran/rulsafe/pull/2).
3. [Installed-demo packaging fix](https://github.com/roshandhanasekaran/rulsafe/pull/3).
4. [Physical NASA battery integration check](https://github.com/roshandhanasekaran/rulsafe/pull/4).
5. Candidate metadata, distribution checks, private build artifacts, and this
   release procedure (the release-preparation PR).
6. The follow-up grouping correction and independent review record: reject
   unsupported grouping before fitting and preserve physical-machine identity
   when supplying partitions for repaired episodes.

Retarget dependent PRs as their bases merge. Do not squash a dependent base
without preserving or rebasing its dependent commits. The final merged commit
must pass CI and be the source for the eventual release artifacts.

Read the [critical review and validation record](release-review-v0.1.0.md).
The v0.1 contract is completed-trajectory RUL. `failure_within_horizon`, native
calendar-date parsing, censored-fleet classification, global-time splits,
alerts, and generic `check`/`train` CLI execution remain unimplemented.
Do not advertise those features when making this candidate public.

## Build without publishing

Use Python 3.12 and the audited lock that CI uses:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes --only-binary=:all: -r requirements/dev-3.12.lock
python -m pip install --no-deps --no-build-isolation -e .
python -m build --no-isolation
pip-audit --requirement requirements/dev-3.12.lock \
  --disable-pip --require-hashes --progress-spinner=off \
  --format cyclonedx-json --output dist/sbom-build-python-3.12.cdx.json
```

Start with an empty `dist/` or a new checkout so older versions cannot be mixed
into the candidate. Verify the wheel contains the typing marker, two demo YAML
configs, LICENSE, and NOTICE, and no third-party datasets. The sdist contains
first-party synthetic test fixtures; it must not contain downloaded NASA data,
local runs, secrets, or environment files.

Create a separate environment, install the lock and the built wheel there,
then run its installed-package check:

```bash
python -m venv /tmp/rulsafe-wheel-check
/tmp/rulsafe-wheel-check/bin/python -m pip install \
  --require-hashes --only-binary=:all: -r requirements/dev-3.12.lock
/tmp/rulsafe-wheel-check/bin/python -m pip install --no-deps dist/rulsafe-0.1.0-py3-none-any.whl
/tmp/rulsafe-wheel-check/bin/python scripts/check_installed_distribution.py
```

The script itself runs the installed CLI in a fresh directory and checks the
version, metadata, resources, synthetic report, and missing-FD001 error. It
rejects importing the source checkout. Also install the sdist in a separate
environment and repeat. With a separate installation of Twine 7.0.0, run
`twine check --strict dist/*.whl dist/*.tar.gz`. This checks package metadata
and Markdown rendering; it does not upload anything.

Repeat the full test suite on Python 3.11, 3.12, and 3.13 with each matching
lock. Install Gitleaks with `bash scripts/install-gitleaks.sh` and put its
installation directory on PATH. Run pre-commit, Ruff, mypy, Bandit, the
full-history Gitleaks scan, and each lock's dependency audit. Reproduce the
[FD001 evaluation](../benchmarks/verification-cb1136e.md) and, optionally, the
[physical battery smoke check](../benchmarks/nasa-battery-smoke.md).

CI's build job retains the sdist, wheel, SHA256SUMS, and an audited CycloneDX
JSON SBOM as a workflow artifact for review. The SBOM describes the entire
Python 3.12 build/development lock, including tooling; it is not a runtime-only
SBOM. Artifact storage inherits repository access, and retention is limited.
There is no publishing job, `id-token: write` permission, or PyPI credential.

## After explicit owner approval

The following remain separate owner-controlled release actions:

- Approve and merge the reviewed PRs; confirm the final `main` commit's CI.
- Approve repository visibility separately, including the history and licence.
- Confirm ownership/availability of the PyPI project name. The read-only
  `rulsafe` project lookup returned HTTP 404 on 2026-11-08; this is not a
  reservation or a guarantee the name can be registered.
- Set an actual release date in CHANGELOG/CITATION only when releasing.
- Configure PyPI trusted publishing with a protected `pypi` environment and
  explicit approval. Do not paste or commit publishing tokens.
- Build and review artifacts from the approved final commit, verify hashes,
  then authorize tagging and publication as separate actions.

[ADR-010](decisions/ADR-010-security-supply-chain.md) remains Proposed. Its
SBOM recommendation is implemented by the candidate build job, but trusted
publishing and maintainer acceptance are still deferred. No approval to
publish or change visibility is implied by preparing the candidate.
