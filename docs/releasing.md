# Preparing and reviewing v0.1.0

Version 0.1.0 was approved for release on 2026-11-08. This procedure records
the review and publication controls used for the release.

## Review the changes

PRs 1–16 are merged on `main`. The following list records the final
release-hardening sequence and the scope reviewed in each PR:

1. [Strict runtime table contract](https://github.com/roshandhanasekaran/rulsafe/pull/7).
2. [NASA milling physical-data smoke check](https://github.com/roshandhanasekaran/rulsafe/pull/8).
3. [Reject v0.1 configuration options without runtime behavior](https://github.com/roshandhanasekaran/rulsafe/pull/9).
4. [Preserve configured report metadata and ordering](https://github.com/roshandhanasekaran/rulsafe/pull/10).
5. [Make the isolated mypy pre-commit hook reproducible](https://github.com/roshandhanasekaran/rulsafe/pull/11).
6. [Complete the exported report writers](https://github.com/roshandhanasekaran/rulsafe/pull/12).
7. [Documentation consistency and final review record](https://github.com/roshandhanasekaran/rulsafe/pull/13).
8. [Record the merged release candidate](https://github.com/roshandhanasekaran/rulsafe/pull/14).
9. [Make the release gate durable](https://github.com/roshandhanasekaran/rulsafe/pull/15).
10. [Trusted PyPI publishing](https://github.com/roshandhanasekaran/rulsafe/pull/16).

They were merged in the order above. Conflict resolution retained every
overlapping `CHANGELOG.md` entry, both the audit-policy and report-metadata
updates in `README.md`, PR 7's `math` import, and PR 12's removal of the unused
`json` import in `pipeline/execute.py`. The complete matrix then passed on the
integrated `main` commit. Build eventual release artifacts only from the exact
approved commit, including any later documentation-only changes.

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

Build from a fresh checkout of the exact approved commit and start with an
empty `dist/`; emptying `dist/` in a worktree used for tests is not an
equivalent release source. Verify the wheel contains the typing marker, two
demo YAML configs, LICENSE, and NOTICE, and no third-party datasets. The sdist
contains first-party synthetic test fixtures; reject it if it contains test
caches such as `.hypothesis`, `.pytest_cache`, `.coverage*`, or `__pycache__`,
or any downloaded NASA data, local runs, secrets, or environment files.

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
[FD001 evaluation](../benchmarks/verification-cb1136e.md) and review the
optional [physical-data integration checks](../benchmarks/README.md).

CI's build job retains the sdist, wheel, SHA256SUMS, and an audited CycloneDX
JSON SBOM as a workflow artifact for review. The SBOM describes the entire
Python 3.12 build/development lock, including tooling; it is not a runtime-only
SBOM. Artifact storage inherits repository access, and retention is limited.

`.github/workflows/publish.yml` runs only for a published GitHub Release. Its
build job rechecks the exact tag and retains distributions separately from
checksums and the SBOM. Its publish job has the only `id-token: write`
permission and uses the protected `pypi` environment and a pinned trusted-
publishing action. The repository stores no PyPI credential.

## Publication checklist

The following owner-controlled release actions complete publication:

- Confirm the approved final `main` commit's CI and rebuilt candidate artifacts.
- Approve repository visibility separately, including the history and licence.
- Confirm ownership/availability of the PyPI project name. The read-only
  `rulsafe` project lookup returned HTTP 404 on 2026-11-08; this is not a
  reservation or a guarantee the name can be registered.
- Configure the PyPI pending publisher for repository `rulsafe`, workflow
  `publish.yml`, and environment `pypi`. Protect that GitHub environment with
  explicit approval. Do not paste or commit publishing tokens.
- Build and review artifacts from the approved final commit, verify hashes,
  then authorize tagging and publication as separate actions.

[ADR-010](decisions/ADR-010-security-supply-chain.md) is Accepted. Its SBOM and
trusted-publishing controls are implemented. The environment and PyPI
publisher remain account-level release controls.
