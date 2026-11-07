#!/usr/bin/env bash
# Install or update Gameday Lights as a systemd --user service (Linux). Safe to rerun.
#
#   deploy/install.sh [--pull] [--skip-tests] [--no-restart] [--dry-run]
#
#   --pull        git pull --ff-only first (update to the latest commit)
#   --skip-tests  don't run the test suite before (re)starting
#   --no-restart  install/update but leave a running service alone
#   --dry-run     print what would happen; change nothing
set -euo pipefail

PULL=0; SKIP_TESTS=0; NO_RESTART=0; DRY=0
for arg in "$@"; do
  case "$arg" in
    --pull) PULL=1 ;;
    --skip-tests) SKIP_TESTS=1 ;;
    --no-restart) NO_RESTART=1 ;;
    --dry-run) DRY=1 ;;
    -h|--help) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE="gameday-lights"
TEMPLATE="$REPO/deploy/systemd/$SERVICE.service"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT="$UNIT_DIR/$SERVICE.service"
export PATH="$HOME/.local/bin:$PATH"

step() { printf '\n==> %s\n' "$*"; }
note() { printf '    %s\n' "$*"; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
run()  { if [ "$DRY" = 1 ]; then note "[dry-run] $*"; else "$@"; fi; }

step "Preflight"
[ "$(uname -s)" = "Linux" ] || die "this script is for Linux + systemd (macOS and Windows installers come later)"
command -v systemctl >/dev/null || die "systemctl not found"
systemctl --user show-environment >/dev/null 2>&1 \
  || die "no systemd user session reachable; log in graphically or via a full login shell"
command -v uv >/dev/null || die "uv not found. Install it from https://docs.astral.sh/uv/ and rerun"
[ -f "$TEMPLATE" ] || die "missing $TEMPLATE"
note "repo:  $REPO"
note "uv:    $(uv --version)"
cd "$REPO"

if [ "$PULL" = 1 ]; then
  step "Updating code (git pull --ff-only)"
  [ -d .git ] || die "not a git checkout"
  run git pull --ff-only
fi

step "Installing dependencies (uv sync --frozen)"
run uv sync --frozen

step "Config"
if [ ! -f config.toml ]; then
  run cp config.example.toml config.toml
  note "created config.toml from config.example.toml"
  if [ "$DRY" != 1 ]; then
    echo "Edit config.toml (bulb IP/MAC, teams, colors, delay_s), then rerun this script." >&2
    echo "Tip: 'uv run gameday-lights discover' prints your bulb's IP and MAC." >&2
    exit 1
  fi
fi
if [ -f config.toml ]; then
  run uv run --frozen python -c \
    "from app.config import load_config; c = load_config('config.toml'); \
print('config ok:', len(c.teams), 'team(s),', len(c.bulbs), 'bulb(s), dispatch_enabled =', c.general.dispatch_enabled)"
fi

if [ "$SKIP_TESTS" = 0 ]; then
  step "Running tests"
  run uv run --frozen pytest -q
fi

step "Installing systemd user unit"
RENDERED="$(mktemp)"; trap 'rm -f "$RENDERED"' EXIT
sed "s|%h/hack/gameday-lights|$REPO|g" "$TEMPLATE" > "$RENDERED"
if [ ! -f "$UNIT" ] || ! cmp -s "$RENDERED" "$UNIT"; then
  run mkdir -p "$UNIT_DIR"
  run install -m 0644 "$RENDERED" "$UNIT"
  run systemctl --user daemon-reload
  [ "$DRY" = 1 ] || note "installed $UNIT"
else
  note "unit already up to date"
fi
run systemctl --user enable "$SERVICE.service"

step "Starting service"
if systemctl --user is-active --quiet "$SERVICE.service"; then
  if [ "$NO_RESTART" = 1 ]; then
    note "running; left alone (--no-restart). Restart later: systemctl --user restart $SERVICE"
  else
    note "restarting. Scores that happen while it restarts are recorded but never fire,"
    note "so avoid restarting mid-game (use --no-restart)."
    run systemctl --user restart "$SERVICE.service"
  fi
else
  run systemctl --user start "$SERVICE.service"
fi

step "Linger (run when logged out)"
if [ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null || echo unknown)" = "yes" ]; then
  note "enabled"
else
  note "not enabled. To keep it running after logout:  loginctl enable-linger $USER"
fi

step "Status"
if [ "$DRY" = 1 ]; then
  note "[dry-run] done; nothing was changed"
else
  sleep 2
  systemctl --user --no-pager --lines=0 status "$SERVICE.service" || true
  echo; journalctl --user -u "$SERVICE" --no-pager -n 8 || true
  echo; echo "Follow logs:  journalctl --user -u $SERVICE -f"
fi
