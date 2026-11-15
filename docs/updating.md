# Keeping it up to date

Updating is manual: nothing changes on your computer until you run the installer again. (You
may get a message saying a new version is out; a new version is never installed for you.)

## Mac

Run the same install line again:

```bash
curl -fsSL https://github.com/notoriousWRG/gameday-lights/releases/latest/download/bootstrap.sh | sh
```

It installs the newest release over the old one, keeps your settings and history, and
restarts the app. Open the **Diagnostics** tab afterward to see the new version number.

The release notes for every version are on the
[releases page](https://github.com/notoriousWRG/gameday-lights/releases); they say what changed and
whether you need to do anything.

!!! note "It won't update during a game"
    The app restarts when it updates, and a score that happens during the restart wouldn't
    light. So if a game is being watched, the installer stops and tells you to run it again
    afterward. Add `--force` only if you don't mind missing a score:

    ```bash
    curl -fsSL https://github.com/notoriousWRG/gameday-lights/releases/latest/download/bootstrap.sh | sh -s -- --force
    ```

## Going back to an older version

Name the version you want:

```bash
curl -fsSL https://github.com/notoriousWRG/gameday-lights/releases/latest/download/bootstrap.sh | sh -s -- --version v0.1.0
```
