# Changelog

One section per release, newest first. The section for a version is its GitHub Release notes,
so write it for the person updating: what changed for them, and anything they must do.

## 0.1.0 (unreleased)

First packaged release.

- Follows NFL and NHL teams through ESPN and flashes a smart bulb in team colors on a score,
  after a delay that matches a streamed TV picture.
- Web page on your home network: Teams, Bulbs, Lights, Effects, Calibrate, Settings, Advanced
  and Diagnostics.
- WiZ bulbs and Govee bulbs and strips (including chase effects).
- Calibrate screen with practice mode, to measure how far your stream trails live.
- Diagnostics tab with a "copy for text message" button, an optional heartbeat ping and
  optional failure messages (webhook or email).
- `gameday-lights init` and `doctor`, and a per-user data folder on each OS.
- Installer for macOS and Linux (`bootstrap.sh`); rerun it to update.
