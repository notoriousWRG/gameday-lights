# Card: build and discover bulbs by kind

**Target files:** app/main.py, tests/test_main.py
**Goal:** `make_bulb` builds a `GoveeBulb` for `kind = "govee"`, and discovery (CLI and web) returns WiZ and Govee bulbs together, each tagged with its kind.

## Contract
- `make_bulb` dispatches on `BulbConfig.kind`; dry-run is unchanged
- `discover_all(broadcast) -> list[dict]` runs `discover_wiz` and `discover_govee` concurrently, tags each result `kind`, and one brand failing does not hide the other's results (both failing raises)
- `main.py` passes `discover_all` to `create_app`; `gameday-lights discover` prints both kinds with their `kind`

## Constraints
- Tests use fakes, no network. Do not touch the adapters or web files.

## Done when
- [ ] `uv run pytest` and `uv run ruff check` pass
- [ ] Only the target files changed
