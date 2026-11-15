# Card: Failure notifier (webhook, then email)

**Target files:** app/notify.py (new), app/config.py, app/settings.py, config.example.toml, app/main.py, app/settings.py, app/settings_service.py (health is a TOML-only machine setting; the monitor reads watcher stats, so watcher.py is untouched), tests/test_notify.py (new)
**Goal:** When ESPN has failed for `fail_after_min` minutes or a followed team's bulb is unreachable that long, send one short message through the configured notifier; send a recovery message when it clears. Never repeat more than once per `renotify_min`.

## Contract
- `Notifier` protocol with `async send(subject, body)`; implementations `WebhookNotifier` (POST JSON) and `SmtpNotifier` (stdlib smtplib in a thread)
- SMTP password is a secret: write-only in settings, never in diagnostics or exports with `--no-secrets`

## Constraints
- Optional: no notifier configured means log-only. Thresholds are config values.

## Done when
- [ ] pytest and ruff pass (fake SMTP and fake transport; no network)
