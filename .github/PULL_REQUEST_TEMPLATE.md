## Summary

## Scope

- [ ] This stays inside v0.1 (completed trajectory, C-MAPSS FD001 or synthetic fixtures), or it is an explicit v0.2 change.
- [ ] Censored and unsupported histories are rejected or reported. Nothing is dropped silently.
- [ ] No persistence baseline, no linear interpolation, no web UI, no warehouse driver, no AutoGluon.
- [ ] No third-party dataset files, secrets, or access keys.
- [ ] C-MAPSS licence text still says "not specified" on the NASA catalog, with the Zenodo CC BY 4.0 note kept separate.

## Checks

- [ ] `ruff check` and `ruff format --check`
- [ ] `mypy src`
- [ ] `pytest`
