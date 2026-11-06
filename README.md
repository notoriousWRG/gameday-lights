# Game Lights

A small home server that watches your teams' games through ESPN's unofficial API and pulses a smart bulb in team colors when they score, delayed to land with a streamed TV picture.

Status: Phase 0/1 in development (WiZ bulbs, NFL first). See `intent.md` for the vision and `PLAN.md` for progress.

## Development

```bash
uv sync
uv run pytest
uv run ruff check
```

Copy `config.example.toml` to `config.toml` (once it exists) for local settings; `config.toml` is gitignored.

## License

MIT
