# Install on a Mac

This takes about 5 minutes. You don't need to be an administrator, and nothing is installed
system-wide.

!!! warning "Pre-release"
    Version 0.1.0 isn't out yet, so the normal line below won't work yet. If you're trying the
    pre-release, use the line under *Pre-release install* instead.

## Before you start

1. **Put the bulb on your Wi-Fi** with its own phone app (WiZ or Govee). It must be on the
   same network as the Mac. WiZ and Govee bulbs only use the **2.4 GHz** band.
2. **Turn on local control** in that app. Gameday Lights talks to the bulb directly over your
   home network, and the bulbs ship with that switched off or restricted:
    - **WiZ:** in the WiZ app, open Settings > Security and turn **off** "only allow verified
      controls".
    - **Govee:** in the Govee app, open the device's settings and turn on **LAN Control**.
3. Make sure the Mac will be **on during games**. A Mac mini that's always on is ideal.

## Install

1. Open **Terminal**: press `Cmd` + `Space`, type `Terminal`, press `Return`.
2. Paste this line and press `Return`:

    ```bash
    curl -fsSL https://github.com/notoriousWRG/gameday-lights/releases/latest/download/bootstrap.sh | sh
    ```

3. Wait. It prints each step as it goes: it installs a small helper called uv, installs
   Gameday Lights, creates your settings and sets the app to start whenever you log in.

When it finishes, a browser window opens on your Gameday Lights page. That's the app.

??? note "Pre-release install"
    ```bash
    curl -fsSL https://github.com/notoriousWRG/gameday-lights/releases/download/v0.1.0rc1/bootstrap.sh | sh -s -- --version v0.1.0rc1
    ```

    To remove a pre-release:

    ```bash
    curl -fsSL https://github.com/notoriousWRG/gameday-lights/releases/download/v0.1.0rc1/bootstrap.sh | sh -s -- --uninstall
    ```

!!! note "If macOS asks about the local network"
    macOS may ask whether Terminal (or Python) can find and connect to devices on your local
    network. Choose **Allow**. Gameday Lights needs that to talk to your bulb. If you missed
    it, open System Settings > Privacy & Security > Local Network and switch it on there.

## Check that it's running

- The page at <http://127.0.0.1:8787/> loads. Bookmark it.
- Open the **Diagnostics** tab. It shows the version and whether your bulb answers.

To check from Terminal as well:

```bash
~/.local/bin/gameday-lights doctor
```

Each line starts with `ok`, `warn` or `FAIL`. A `warn` that port 8787 is "already in use" just
means the app is already running. That's good.

## What happens next

- **It starts by itself** whenever you log in to the Mac, and restarts if it stops.
- **It keeps the Mac awake** while it runs, but it can't work if the Mac is shut down or
  logged out. If this is an always-on Mac mini, turn on automatic login (System Settings >
  Users & Groups) so it comes back after a power cut.
- **Your settings and history** live in `~/Library/Application Support/gameday-lights`. The
  log is `~/Library/Logs/gameday-lights.log`.

Next: **[set it up](first-setup.md)**.

## Removing it

```bash
curl -fsSL https://github.com/notoriousWRG/gameday-lights/releases/latest/download/bootstrap.sh | sh -s -- --uninstall
```

This stops the app and removes the program. Your settings and history are kept, and the
command tells you which folder to delete if you want them gone too.
