# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.1] - 2026-04-30

### Fixed
- `--wallet` mode: pagination no longer raises `HTTPError 400` when the wallet has fewer
  than `max_pages × limit_per_page` trades. The CLOB data-api returns 400 on `offset`
  past the wallet's last trade; this is now treated as end-of-pagination instead of an
  error (only after at least one page has been pulled successfully).

### Added
- `examples/sample_report_stranger_wallet.md` — a redacted sample audit run against a
  random Polymarket wallet (65 trades, +$32 DB-reported / −$30 chain / **−$62.66 hidden
  slippage**), demonstrating the slippage gap is not specific to one bot.

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

[0.1.1]: https://github.com/LuciferForge/pnl-truthteller/releases/tag/v0.1.1
[0.1.0]: https://github.com/LuciferForge/pnl-truthteller/releases/tag/v0.1.0
