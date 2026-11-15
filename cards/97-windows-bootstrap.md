# Card: Windows bootstrap installer

**Target files:** deploy/bootstrap.ps1 (new), deploy/windows/README-firewall.md (new), tests/test_deploy_templates.py
**Goal:** `irm <release url>/bootstrap.ps1 | iex` installs uv (user scope, no admin), `uv tool install` of the tagged wheel, `gameday-lights init`, registers a Task Scheduler task "Gameday Lights" that runs at logon, restarts on failure and hides the console, then starts it and opens the web page. Rerun updates; `-Uninstall` removes the task (data kept unless `-Purge`).

## Constraints
- No admin rights needed; if the Windows Firewall prompt appears for local UDP the script tells the user to choose **Private networks** and Allow.
- Pin the task to the installed exe path; handle spaces in the user name. PowerShell 5.1 compatible (what Windows ships).
- Cannot be run from this machine: keep it short and readable, include `-DryRun`, and lint the template with a text test.

## Done when
- [ ] pytest and ruff pass
- [ ] Real run on a Windows PC (user): zero to web page, then reboot test
