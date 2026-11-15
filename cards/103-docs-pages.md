# Card: Friends-and-family docs

**Target files:** docs/install-mac.md, docs/install-windows.md, docs/install-linux.md, docs/first-setup.md, docs/bulbs.md, docs/updating.md, docs/troubleshooting.md, docs/faq.md (all new), mkdocs.yml (nav)
**Goal:** Plain-language pages written for someone who has never seen a terminal: one install page per OS (one pasted line, what to expect, the firewall/local-network prompt with screenshots as TODO placeholders), first setup (join the bulb to Wi-Fi with its vendor app and turn on LAN control, open the web page, follow a team, add the bulb, press Test), game day and delay tuning link, updating (rerun the one-liner), and troubleshooting (bulb not found, no lights, wrong delay, how to copy the Diagnostics bundle and text it to me).

## Constraints
- No team, brand or household assumptions. Commands in fenced blocks, one per block.

## Done when
- [ ] `mkdocs build --strict` passes; user walks first-setup on a clean machine and lists confusing steps
