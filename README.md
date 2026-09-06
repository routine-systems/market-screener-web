# market-screener-web

Cloudflare Pages presentation for `screener.chiragpatnaik.com`.

This repository accepts one immutable `signals-bundle.v1.json` artifact. It does not scrape
Chartink or open local market databases. The renderer validates the bundle's major schema version
before building the twelve-page dashboard shell.

The HT page is independent of the Chartink bundle. It reads one rolling snapshot
from the existing `SCANLINKS` KV binding through `GET /api/tsha-hbcs`. The browser
cannot trigger a scan or a write. The local market process replaces the single
snapshot after the India evening run and the US morning run. Each market/timeframe
bucket carries up to 13 completed periods. Exact market and timeframe selections
can step backward or select 1, 3, 5, 8, or 13 periods. Replayed periods are labeled
separately from stored historical outputs. The compact table omits the Name column.

The VT page follows the same read-only snapshot pattern through
`GET /api/volume-trend`. Its independent snapshot contains India/US Daily/Weekly
BUY and SELL events plus a compact 13-period history.

The Clusters page is a research-only view built from those same HT and VT
snapshots. It retains the policy-driven Shortlist. Its HT cohorts require a
current HT signal with at least 2 appearances in 3 periods or 3 in 5 periods.
Its HT + VT cohort additionally requires a confirmed VT BUY on that period or
either of its two preceding same-timeframe periods. The scheduled refresh runs
the cluster regression contract before every production deployment.

Production runs from the public `.github/workflows/refresh.yml` orchestrator. It checks out the
public `routine-systems/market-signals` producer at `main`, creates a fresh bundle, verifies its expected
session when requested, renders the twelve pages, and deploys that same build to the existing
Cloudflare Pages project.

Production UI changes must use `refresh.yml`. A direct deployment of a local `dist/` can replace
fresh signals with an older ignored bundle. The local build command therefore requires an explicit
immutable bundle path and does not select `artifacts/signals-bundle.v1.json` by default.

The root Pages middleware rejects every hostname except `screener.chiragpatnaik.com`. Cloudflare
Access protects that custom hostname. Immutable `pages.dev` deployment aliases cannot reach the
static pages or dispatch Functions.

## Local build

```bash
./scripts/build tests/fixtures/signals-bundle.v1.json
python3 -m unittest discover -s tests -v
```

The default weekly view is eight weeks. `dist/build-manifest.json` records the input checksum and
producer commit for deployment provenance.

## Deployment boundary

The Pages project remains `screener`. GitHub stores only the scoped `CLOUDFLARE_API_TOKEN` Actions
secret. This repository contains no market database and performs no R2 or D1 writes. The
TSHA-HBCS API performs one KV read per page load and never polls.
