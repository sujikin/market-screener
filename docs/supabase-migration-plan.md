# Supabase Migration for Nightly Monitor Data

## Decision
- Make Supabase the primary store for `Market Monitor` data only. Keep the `Custom Scan` path exactly as it is in v1.
- Keep the current Python nightly pipeline and GitHub Actions scheduler. Do not move nightly compute to Edge Functions or `pg_cron` in v1.
- Model long history separately from daily published scan runs:
  - Canonical incremental `ticker_price_history` keyed by `(ticker, trade_date)`.
  - Immutable daily `snapshot_runs` and related per-run tables for the published monitor output.
- Migrate with dual-publish first: continue generating local files and publishing to Supabase. After 10 consecutive successful weekday runs with parity checks, stop nightly git commits of generated data.
- If git exports remain, generate them from the current published run pointer only. Do not treat git as the source of truth.

## Current State Findings
- `nightly_scan.py` currently overwrites the latest CSV and JSON artifacts for each universe on every successful run.
- `screener.py` is hard-coded to fetch `LOOKBACK_PERIOD = "1y"` today.
- The current one-year local caches already hold about `12.3k` rows for `nifty50` and `12.1k` rows for `niftynext50`, while the published scan CSVs hold fewer than `50` rows each. This is the main reason git should not remain the canonical history store.
- The monitor app is built around a current published snapshot plus grouped ticker history. It is not yet a general historical query system.
- The UI chart windows are currently `3M`, `6M`, and `1Y`. A five-year store is therefore an infrastructure decision for future flexibility, not a current UI requirement.
- The index screener only needs about `200` sessions of history for its current indicators. Retention horizon and indicator minimum are different concerns and should be modeled separately.
- Fundamentals are best-effort and are currently generated only for screened tickers. They should not be treated as the canonical long-history layer.
- Historical index membership is out of scope unless a dated constituent history table is added. The current code works from the present constituent set.

## Architecture
- Use a Supabase project in `South Asia (Mumbai)` as the primary region.
- Use Postgres for canonical monitor data and a private Storage bucket for raw artifact archives.
- Keep base app behavior unchanged:
  - `nightly_scan.py` still generates the same 8 artifacts locally during migration.
  - `app.py` monitor tab still reads `UniverseSnapshot`, grouped history DataFrames, and fundamentals payloads.
  - `custom` scans remain local/live and are not routed through Supabase.

### Data model
- `snapshot_runs`
  - One row per universe publish attempt.
  - Columns: `id`, `universe_key`, `generated_at`, `market_data_date`, `screened_count`, `constituent_count`, `action_counts_json`, `status`, `source_commit_sha`, `artifact_prefix`, `error_message`.
- `published_universe_runs`
  - One row per universe: `universe_key`, `run_id`, `published_at`.
  - This is the only pointer the app and any export jobs trust for "current" data.
- `snapshot_rows`
  - Screened rows for a run.
  - Columns mirror current CSV fields: `stock`, `ticker`, `close`, `adj_close`, `rsi`, `vol_spike`, `action`, `return_1y_pct`, `rank`.
  - Primary key: `(run_id, ticker)`.
- `snapshot_missing_constituents`
  - Per-run missing constituents with `ticker`, `stock`, `reason`, `history_days`.
- `snapshot_fundamentals`
  - Per-run fundamentals for screened tickers only.
  - Columns: `run_id`, `ticker`, `provider`, `status`, `roe`, `roce`, `debt_equity`, `operating_margin`, `sales_growth`, `profit_growth`, `pe_ratio`.
  - This table is for daily presentation parity, not for authoritative historical analytics.
- `ticker_price_history`
  - Canonical OHLCV history used to support 5Y+ retention without duplicating the full history inside every daily run.
  - Columns: `ticker`, `trade_date`, `open`, `high`, `low`, `close`, `adj_close`, `volume`, `split`, `source`, `last_refreshed_at`.
  - Primary key: `(ticker, trade_date)`.
- `universe_membership_history` (optional)
  - Only needed if the project later needs historically correct constituent membership for backtests or "what was in the index on date X?" queries.
  - Columns: `universe_key`, `ticker`, `stock`, `effective_from`, `effective_to`.

### Price ingestion rules
- Run a one-time bootstrap/backfill to at least `5Y` for the tracked monitor tickers.
- Nightly ingest should be incremental for the latest trading day, but not strictly append-only.
- Refresh a rolling repair window for recent history because adjusted prices can change after splits, dividends, or provider normalization updates.
- Keep the canonical history universe-agnostic by ticker. A ticker may appear in different monitor universes over time.
- Current scale is small enough for five years to be comfortable, but if universes expand materially the app should stop eagerly loading full grouped history for every ticker on every monitor page load.

### Storage archive
- Private bucket: `snapshot-artifacts`.
- Path layout: `/{universe_key}/{generated_at_iso_or_run_id}/latest_scan.csv`, `snapshot_meta.json`, `fundamentals_cache.json`, `price_cache.csv`.
- Purpose: rollback, audit, re-import, and exact raw-file preservation after git commits are retired.

### Read/write interface changes
- No UI model changes.
- Keep existing loader return types unchanged.
- Add environment config:
  - `SNAPSHOT_BACKEND=auto|file|supabase` with default `auto`
  - `SUPABASE_URL`
  - `SUPABASE_ANON_KEY` for app reads
  - `SUPABASE_SERVICE_ROLE_KEY` for nightly publishes only
- Implement a repository dispatch layer:
  - File backend remains current behavior.
  - Supabase backend returns the same `UniverseSnapshot`, grouped cache dict, and fundamentals payload format.
  - The Supabase history loader should derive grouped ticker history from `ticker_price_history` for the tickers in the current published run, not from a duplicated per-run history table.

### Export and git policy
- Separate compute/publish from export.
- Primary nightly job:
  - Refresh and repair canonical price history.
  - Compute the daily scan.
  - Publish the current run in Supabase.
- Optional secondary export job:
  - Reads only `published_universe_runs`.
  - Regenerates `latest_scan_*.csv`, `snapshot_meta_*.json`, `fundamentals_cache_*.json`, and any trimmed fallback cache from the published data.
  - Commits only if the exported files changed.
- Do not commit the full `5Y+` canonical history dump to git every night.
- Git exports are fallback distribution artifacts, not the authoritative datastore.

### Security
- App reads use `anon` key only.
- Nightly workflow writes use `service role` key only.
- Enable RLS on exposed tables.
- `anon` and `authenticated` get `SELECT` only for rows belonging to the current `published_universe_runs.run_id`, plus the price-history slice needed by that run.
- No browser/app write path in v1.
- Storage bucket stays private; the app does not read artifacts from Storage in normal operation.

## Migration Sequence
1. Provision the Supabase project, create the tables, indexes, RLS policies, and the private artifact bucket.
2. Add a one-time bootstrap script that publishes the current repo artifacts as the first Supabase run for each universe.
3. Add a one-time historical backfill into `ticker_price_history` to at least `5Y` for the tracked monitor tickers.
4. Extend the nightly pipeline to publish one universe at a time:
   - Refresh canonical price history for the latest trading day plus the repair window.
   - Create `snapshot_runs` row with `status='building'`.
   - Insert `snapshot_rows`, `snapshot_missing_constituents`, and `snapshot_fundamentals`.
   - Export the same local artifacts during migration and upload them to Storage.
   - Validate staged Supabase data against the locally generated artifacts.
   - Update `published_universe_runs`.
   - Mark the run `published`.
5. Keep the current file writes and git commit step during migration. Supabase publish is additive at this stage.
6. Add Supabase-backed loaders behind the existing repository functions. `SNAPSHOT_BACKEND=auto` should prefer Supabase when configured, otherwise fall back to files.
7. Add a separate export job that rebuilds lightweight git artifacts from the published run pointer.
8. After 10 consecutive successful weekday runs with parity checks for both universes, remove nightly git data commits from the compute job. Keep the export job only if git-backed fallback artifacts are still needed.
9. Keep the file backend code for local/dev fallback, but treat Supabase as the production source of truth.

### Publish semantics
- Publish each universe independently.
- If `nifty50` succeeds and `niftynext50` fails, only the successful universe pointer advances.
- A failed or partial run must never become visible to the app.
- Old published data remains live until a new run passes validation and the pointer swap completes.
- The export job must read only from the published pointer. It must never export in-flight staging data.

### Retention
- Keep canonical `ticker_price_history` long term, subject to storage cost and provider constraints.
- Keep published and failed run metadata in Postgres.
- Keep per-run tables (`snapshot_rows`, `snapshot_fundamentals`, `snapshot_missing_constituents`) for the latest `30-90` published runs per universe.
- Purge `building` and `failed` runs older than 7 days.
- Keep raw artifact archives in Storage for 365 days.
- Do not store duplicated per-run full price history once `ticker_price_history` exists.

## Test Plan
- Repository parity tests:
  - Same fixture data loaded from file backend and Supabase backend must produce identical `UniverseSnapshot`, grouped cache, and fundamentals payloads.
- Publish flow tests:
  - Partial publish never advances the pointer.
  - One-universe failure does not block the other universe.
  - Re-running the publish step creates a new run without corrupting the current published one.
- Incremental history tests:
  - Historical backfill plus nightly repair does not duplicate `(ticker, trade_date)` rows.
  - Recent rows can be corrected when adjusted prices change.
- Data parity validation:
  - Before pointer swap, compare staged Supabase data to local artifacts field-for-field for scan rows, missing constituents, fundamentals, and the exported snapshot history slice.
- Export job tests:
  - Export reads only from `published_universe_runs`.
  - Export never serializes the full `5Y+` canonical history dump into git.
- App behavior tests:
  - `SNAPSHOT_BACKEND=auto` falls back to files when Supabase config is absent.
  - Monitor tab renders the same visible output under file and Supabase backends for the same dataset.
  - `Custom Scan` remains unchanged.
- Security tests:
  - `anon` can read published data only.
  - `anon` cannot read `building` or failed runs.
  - `anon` cannot insert/update/delete.
- Workflow acceptance:
  - During migration, nightly runs still generate and commit local artifacts.
  - After cutover, the compute job publishes to Supabase and the export job, if retained, regenerates git artifacts from published data only.

## Open Questions
- Do we need historical index membership in v1, or is current membership enough for the first release?
- How large should the repair window be given the adjustment behavior of the chosen market-data provider?
- Should the exported fallback cache stay at `1Y` for UI compatibility, or should it expand once the database becomes primary?
- Do we want to persist fundamentals for all constituents or only for screened names?

## Assumptions and Defaults
- Historical database backfill to at least `5Y` for monitor tickers is in scope. Historical git backfill is not.
- `Custom Scan` and live yfinance reads remain out of scope.
- Supabase becomes the production source of truth after validation. Git artifacts are temporary migration fallback or an optional export surface.
- Exact current UI behavior is preserved; changes are limited to storage, repository plumbing, and workflow operations.
