#!/bin/sh
# Install or update Gameday Lights on macOS or Linux, for the current user (no sudo). Safe to
# rerun: running it again updates to the latest release.
#
#   curl -fsSL https://github.com/notoriousWRG/gameday-lights/releases/latest/download/bootstrap.sh | sh
#   curl -fsSL .../bootstrap.sh | sh -s -- --version v0.2.0
#
# Options:
#   --version vX.Y.Z   install that release instead of the latest
#   --no-service       install the program only; don't set up the start-at-login service
#   --force            update even while a game is being watched (a restart skips scores)
#   --replace-service  Linux: overwrite an existing gameday-lights unit this script didn't write
#   --uninstall        stop and remove the service and program (your data folder is kept)
#   --dry-run          print what would happen; change nothing
#
# For testing: GAMEDAY_WHEEL=<path or URL of a wheel> installs that instead of a release, and
# GAMEDAY_OS=Darwin|Linux pretends to be that OS (with --dry-run, to see the service file).
set -eu

REPO="notoriousWRG/gameday-lights"
LABEL="com.gameday-lights"
UNIT="gameday-lights"
MARKER="# managed by gameday-lights bootstrap.sh"
PORT=8787

VERSION=""; SERVICE=1; FORCE=0; REPLACE_SERVICE=0; UNINSTALL=0; DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --version) [ $# -ge 2 ] || { echo "--version needs a value like v0.2.0" >&2; exit 2; }
               VERSION="$2"; shift ;;
    --no-service) SERVICE=0 ;;
    --force) FORCE=1 ;;
    --replace-service) REPLACE_SERVICE=1 ;;
    --uninstall) UNINSTALL=1 ;;
    --dry-run) DRY=1 ;;
    -h|--help) sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
  shift
done

step() { printf '\n==> %s\n' "$*"; }
note() { printf '    %s\n' "$*"; }
die()  { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
run()  { if [ "$DRY" = 1 ]; then note "[dry-run] $*"; else "$@"; fi; }

OS="${GAMEDAY_OS:-$(uname -s)}"
case "$OS" in
  Darwin|Linux) ;;
  *) die "this installer is for macOS and Linux (Windows has its own: see the docs)" ;;
esac
export PATH="$HOME/.local/bin:$PATH"

PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
MAC_LOG="$HOME/Library/Logs/gameday-lights.log"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT_FILE="$UNIT_DIR/$UNIT.service"
if [ -n "${GAMEDAY_HOME:-}" ]; then DATA_DIR="$GAMEDAY_HOME"
elif [ "$OS" = Darwin ]; then DATA_DIR="$HOME/Library/Application Support/gameday-lights"
else DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/gameday-lights"; fi

# ---- the service files (the program's path is filled in) ---------------------------------
render_plist() {
  cat <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/caffeinate</string>
    <string>-i</string>
    <string>$BIN</string>
    <string>run</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>$MAC_LOG</string>
  <key>StandardErrorPath</key><string>$MAC_LOG</string>
</dict>
</plist>
EOF
}

render_unit() {
  cat <<EOF
$MARKER
[Unit]
Description=Gameday Lights (score-triggered bulb effects)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=$BIN run
Restart=on-failure
RestartSec=10
KillSignal=SIGTERM

[Install]
WantedBy=default.target
EOF
}

# ---- helpers -------------------------------------------------------------------------
# Is a game being watched right now? A restart skips any score that lands while it is down.
game_in_progress() {
  status="$(curl -fsS --max-time 3 "http://127.0.0.1:$PORT/api/status" 2>/dev/null)" || return 1
  case "$status" in
    *'"watching":[]'*) return 1 ;;
    *'"watching":['*) return 0 ;;
    *) return 1 ;;
  esac
}

latest_tag() {
  url="$(curl -fsSLI -o /dev/null -w '%{url_effective}' "https://github.com/$REPO/releases/latest")" \
    || return 1
  tag="${url##*/}"
  case "$tag" in v[0-9]*) printf '%s' "$tag" ;; *) return 1 ;; esac
}

stop_service() {
  if [ "$OS" = Darwin ]; then
    launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
  else
    systemctl --user disable --now "$UNIT.service" >/dev/null 2>&1 || true
  fi
}

# ---- uninstall -----------------------------------------------------------------------
if [ "$UNINSTALL" = 1 ]; then
  step "Removing the service"
  if [ "$OS" = Darwin ]; then
    if [ "$DRY" = 1 ]; then note "[dry-run] stop and remove $PLIST"
    else stop_service; rm -f "$PLIST"; note "removed $PLIST"; fi
  elif [ -f "$UNIT_FILE" ] && grep -q "^$MARKER" "$UNIT_FILE"; then
    if [ "$DRY" = 1 ]; then note "[dry-run] stop and remove $UNIT_FILE"
    else
      stop_service; rm -f "$UNIT_FILE"; systemctl --user daemon-reload || true
      note "removed $UNIT_FILE"
    fi
  else
    note "no service installed by this script"
  fi
  step "Removing the program"
  if command -v uv >/dev/null 2>&1; then run uv tool uninstall gameday-lights || true
  else note "uv not found; nothing to remove"; fi
  note "Your settings and history were kept. To delete them too, remove the data folder:"
  note "  $DATA_DIR"
  exit 0
fi

# ---- install / update --------------------------------------------------------------------
step "Checking this computer"
note "system: $OS"
command -v curl >/dev/null 2>&1 || die "curl is required"
if [ "$OS" = Linux ] && [ "$SERVICE" = 1 ] && [ "$DRY" = 0 ]; then
  systemctl --user show-environment >/dev/null 2>&1 \
    || die "no systemd user session here; log in normally (not via sudo) or use --no-service"
fi
if [ "$DRY" = 0 ] && [ "$SERVICE" = 1 ] && [ "$FORCE" = 0 ] && game_in_progress; then
  die "a game is being watched right now, and updating restarts the app (a score during the restart would not light). Run again after the game, or add --force."
fi

step "uv (installs and runs the program)"
if command -v uv >/dev/null 2>&1; then
  note "found $(uv --version)"
elif [ "$DRY" = 1 ]; then
  note "[dry-run] would install uv from https://astral.sh/uv/install.sh"
else
  curl -LsSf https://astral.sh/uv/install.sh | sh
  PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  command -v uv >/dev/null 2>&1 || die "uv installed but not found on PATH; open a new terminal and rerun"
fi

step "Finding the release"
if [ -n "${GAMEDAY_WHEEL:-}" ]; then
  case "$GAMEDAY_WHEEL" in
    http://*|https://*|file://*) SPEC="$GAMEDAY_WHEEL" ;;
    *) SPEC="file://$(cd "$(dirname "$GAMEDAY_WHEEL")" && pwd)/$(basename "$GAMEDAY_WHEEL")" ;;
  esac
  note "using $SPEC"
else
  TAG="$VERSION"
  if [ -z "$TAG" ]; then
    if [ "$DRY" = 1 ]; then TAG="vLATEST"
    else TAG="$(latest_tag)" || die "could not find the latest release on github.com/$REPO"; fi
  fi
  case "$TAG" in v[0-9A-Za-z]*) ;; *) die "version must look like v0.2.0 (got '$TAG')" ;; esac
  SPEC="https://github.com/$REPO/releases/download/$TAG/gameday_lights-${TAG#v}-py3-none-any.whl"
  note "release $TAG"
fi

step "Installing the program"
run uv tool install --force --python 3.12 "gameday-lights @ $SPEC"
if [ "$DRY" = 1 ]; then BIN="$HOME/.local/bin/gameday-lights"
else
  BIN="$(uv tool dir --bin)/gameday-lights"
  [ -x "$BIN" ] || die "install finished but $BIN is missing"
  note "installed: $("$BIN" --version)"
fi

step "Creating your settings"
run "$BIN" init

if [ "$SERVICE" = 0 ]; then
  step "Skipping the service (--no-service)"
  note "Start it yourself with: $BIN run"
  exit 0
fi

step "Setting it to start at login"
if [ "$OS" = Darwin ]; then
  if [ "$DRY" = 1 ]; then
    note "[dry-run] would write $PLIST:"
    echo "----- begin service file -----"; render_plist; echo "----- end service file -----"
  else
    mkdir -p "$(dirname "$PLIST")" "$(dirname "$MAC_LOG")"
    render_plist > "$PLIST"
    stop_service; sleep 1
    launchctl bootstrap "gui/$(id -u)" "$PLIST" \
      || die "could not start the service. Run this from a logged-in desktop session (not over ssh)."
    launchctl kickstart -k "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
    note "wrote $PLIST (logs: $MAC_LOG)"
  fi
else
  if [ -f "$UNIT_FILE" ] && ! grep -q "^$MARKER" "$UNIT_FILE" && [ "$REPLACE_SERVICE" = 0 ]; then
    die "$UNIT_FILE already exists and was not made by this script (a developer checkout?). Use --replace-service to overwrite it, or --no-service."
  fi
  if [ "$DRY" = 1 ]; then
    note "[dry-run] would write $UNIT_FILE:"
    echo "----- begin service file -----"; render_unit; echo "----- end service file -----"
  else
    mkdir -p "$UNIT_DIR"
    render_unit > "$UNIT_FILE"
    systemctl --user daemon-reload
    systemctl --user enable "$UNIT.service" >/dev/null 2>&1
    systemctl --user restart "$UNIT.service"
    note "wrote $UNIT_FILE"
    if [ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null || echo unknown)" != "yes" ]; then
      note "To keep it running when you are logged out:  loginctl enable-linger $USER"
    fi
  fi
fi

step "Checking it started"
if [ "$DRY" = 1 ]; then
  note "[dry-run] done; nothing was changed"
  exit 0
fi
i=0
while [ "$i" -lt 20 ]; do
  if curl -fs -o /dev/null --max-time 2 "http://127.0.0.1:$PORT/"; then
    note "running: open http://127.0.0.1:$PORT/ in a browser"
    note "to check this computer any time:  $BIN doctor"
    [ "$OS" = Darwin ] && open "http://127.0.0.1:$PORT/" >/dev/null 2>&1 || true
    exit 0
  fi
  i=$((i + 1)); sleep 1
done
note "not answering yet. Check:  $BIN doctor"
[ "$OS" = Darwin ] && note "log: $MAC_LOG" || note "log:  journalctl --user -u $UNIT -n 30"
exit 1
