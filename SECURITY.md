# Security

RULSafe reads local CSV and Parquet files and writes a local report. It does not send telemetry to the authors or to a hosted service.

## Supported use

- This is research software, not a safety-certified prognostic. Do not use a report as a substitute for engineering judgement or an OEM procedure.
- Keep data on the machine that runs the check. Caches, once downloads exist, belong under a directory you choose (`~/.cache/rulsafe` or `./rulsafe-runs`).
- Do not put secrets, access keys, or customer identifiers into YAML, HTML, or JSON reports.
- Do not commit third-party dataset files or access keys. SCANIA is CC BY 4.0 and is not part of v0.1. The NASA C-MAPSS catalog page does not state a licence.

## Supply chain

Development dependencies are pinned with hashes in `requirements/dev-3.10.lock`, `requirements/dev-3.11.lock`, `requirements/dev-3.12.lock`, and `requirements/dev-3.13.lock`. CI installs the file that matches the job's Python and audits that file with `pip-audit`. The Python 3.10 lock pins `filelock==4.1.0` because the fixed releases require Python 3.11. Those advisories are named in `requirements/filelock-unfixed-on-3.10.txt` and are not ignored on the other locks. Bandit scans `src/`. Gitleaks scans the full git history in CI. The decision record is [ADR-010](docs/decisions/ADR-010-security-supply-chain.md) (status: Proposed). PyPI publishing is not set up. When it starts, that record recommends trusted publishing and a CycloneDX SBOM from the same lock.

## Reporting a vulnerability

Please do not open a public issue for a security report. Use a private security advisory on the forge that hosts this repository, or contact the maintainers through a private channel if one is published with the repository.

Include what you ran, the version (`rulsafe --version`), and the impact. Do not include customer telemetry or credentials.
