# Market snapshot relay

Private Cloudflare Worker endpoint for local dashboard publishers. The local
machine sends signal snapshots and market-event snapshots.
The Worker can mutate only the existing `SCANLINKS` KV namespace binding. It
hardcodes the signal keys and the market-scoped event keys.

`POST /v1/tsha-hbcs` requires the `INGEST_TOKEN` bearer secret. The relay
validates the exact-body and semantic SHA-256 digests, schema, row counts,
stable row keys, market freshness, and a sequential four-write-per-IST-day
guard. The local publisher serializes both market jobs before this guard. An
identical retry returns `unchanged` without calling `KV.put`. A stale or
conflicting snapshot is rejected. The relay permits one later same-session
revision per market, so the two-hour fallback can replace a partial primary
snapshot. A market-session advance resets that revision allowance. One
catch-up snapshot may advance both markets after the machine restarts.

Each market/timeframe bucket may include one validated `ht-history.v1` block
with at most 13 ordered completed periods. The relay permits one additive
four-bucket history bootstrap when the stored snapshot has no history. The
declared update market may consume its normal same-session revision during
that bootstrap; the other market's latest rows must remain unchanged. The
complete request body remains capped at four MiB.

The Worker has no scheduled trigger. The existing local India and US
LaunchAgents remain the only schedule. The Worker writes neither R2 nor D1.

`POST /v1/market-events` accepts one bounded market snapshot. India contains
separate official NSE/BSE bulk-deal and PIT insider-trade event sets. US contains
source-attributed political-trade reports extracted from the accumulated X
capture. India retains trailing-year counts per category. US retains a
complete-history count. Each value carries the latest 12 details per symbol in
reverse chronological display order. Identical inputs
perform no KV write. US row-count regressions are rejected. Source-cutoff
regressions are rejected for both markets. The relay permits one India
scope-migration write beyond the daily budget when replacing the prior stored
scope with `rolling_1_year`.

The publisher retrieves its bearer value from the macOS Keychain service
`com.chirag.market-snapshot-relay`; the secret never enters a tracked file.

## Validation

```bash
npm test
npm run check
```
