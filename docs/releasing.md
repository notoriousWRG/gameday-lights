# Releasing

For the person publishing Gameday Lights, not for the people running it. Five steps.

1. **Bump the version** in `pyproject.toml` (`0.2.0`, no leading `v`), then run `uv lock` so
   `uv.lock` follows.
2. **Write the changelog.** In `CHANGELOG.md`, rename the top section to `## 0.2.0 (2026-MM-DD)`
   (a heading that starts with the version). That section becomes the release notes: say what
   changed for the people updating, and anything they must do.
3. **Check, commit, push** to `master`:

    ```bash
    uv run ruff check && uv run pytest -q
    ```

4. **Tag and push the tag.** The tag must be `v` plus exactly the version in `pyproject.toml`:

    ```bash
    git tag v0.2.0
    ```

    ```bash
    git push origin v0.2.0
    ```

5. **Verify on the Mac mini first**, before telling anyone. When the *release* workflow in the
   repository's Actions tab turns green, open the release and check it lists the wheel
   (`gameday_lights-0.2.0-py3-none-any.whl`), the sdist and the installers. Then on the Mac
   mini, between games:

    ```bash
    curl -fsSL https://github.com/notoriousWRG/gameday-lights/releases/latest/download/bootstrap.sh | sh
    ```

    Check the web page opens and Diagnostics shows the new version.

## Docs to update at the first real release

When `v0.1.0` (not a pre-release) is published, remove the **Pre-release** warning and the
collapsed *Pre-release install* block from `docs/install-mac.md`. Until then the normal
`releases/latest/...` line has nothing to download.

## What the workflow checks

It stops, publishing nothing, if the tag differs from the `pyproject.toml` version, if lint or
tests fail, if the wheel is not named as the installers expect, or if `CHANGELOG.md` has no
section for the version.

## Trying it without affecting anyone

A tag containing letters, like `v0.2.0rc1` (with `version = "0.2.0rc1"`), publishes as a
**pre-release**. The "latest release" link the installers use skips pre-releases, so nobody
updates by accident. Install one on purpose with `--version v0.2.0rc1`.

## If a release is bad

Delete the release and its tag on GitHub (the previous release becomes "latest" again), and fix
forward with a new version. People already on the bad version rerun the installer, or install a
specific older one with `--version v0.1.0`. Never reuse a version number.
