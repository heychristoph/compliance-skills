## What and why

<!-- What changes, and the reason or ticket. -->

## How it was tested

<!-- Commands run, checks, or what you looked at. -->

## Risk

<!-- Tick what applies and say how it is handled. -->
- [ ] Touches personal or customer data
- [ ] Changes access: IAM, auth, secrets, OAuth scopes, public exposure
- [ ] Needs a manual step or migration (how to roll back: ...)

## Compliance skills

- [ ] Edited `shared/`, then ran `python tools/sync.py` (CI fails on a stale copy)
- [ ] Catalog IDs only added or retired with a replacement, never removed or renamed
- [ ] Report wording changed in every language (`en`, `de`)
- [ ] Oracle evals still score 1.0, and English SOC 2/ISO report data is unchanged unless intended
