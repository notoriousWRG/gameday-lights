# Card: macOS and Linux bootstrap installer

**Target files:** deploy/bootstrap.sh (new), tests/test_deploy_templates.py (new)
**Goal:** `curl -fsSL <release url>/bootstrap.sh | sh` installs uv if missing, runs `uv tool install gameday-lights` from the tagged release wheel, runs `gameday-lights init`, then installs and starts a per-user login service (launchd LaunchAgent on macOS, systemd --user on Linux). Rerun is safe and acts as the updater. Flags: `--version vX.Y.Z`, `--no-service`, `--dry-run`, `--uninstall`.

## Built as
- The two service files are embedded in the script (a `curl | sh` install downloads only that file); tests read them from `--dry-run` output.
- Refuses to update while a game is watched (`--force` overrides) and never overwrites a Linux unit it did not write (`--replace-service`).
- The wheel comes from `releases/download/vX.Y.Z/gameday_lights-X.Y.Z-py3-none-any.whl`: C101 must attach it under exactly that name.

## Constraints
- Not the existing deploy/install.sh (that is the dev-checkout flow; leave it).
- Service runs `gameday-lights run` with the data dir from C94; logs to the data dir on macOS. Uses an absolute path to the installed binary.
- Template test renders each file with a sample path and checks no `%h`/`~` leaks.

## Done when
- [ ] pytest and ruff pass; `--dry-run` changes nothing
- [ ] Real run on the Mac mini (user): web page opens, service survives a reboot
