# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-04-28

### Added
- Initial public release.
- Three input modes:
  - `--wallet 0x...` — fetch fills directly from Polymarket CLOB data-api (no API key needed).
  - `--sqlite ... --positions ...` — read from a bot's local SQLite + positions.json.
  - `--trades ... --fills ...` — JSONL files for custom integrations.
- Order-ID dedup eliminates double-counting from sweep retries.
- Markdown report generation with by-exit-reason breakdown, worst-10 trades, dust shares stranded.
- 8/8 unit tests including dedup, paper-era exclusion, and dust accounting.
- MIT license, zero runtime dependencies (just `requests`).

[0.1.0]: https://github.com/LuciferForge/pnl-truthteller/releases/tag/v0.1.0
