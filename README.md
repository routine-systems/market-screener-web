# market-screener-web

Cloudflare Pages presentation for `screener.chiragpatnaik.com`.

This repository accepts one immutable `signals-bundle.v1.json` artifact. It does not scrape
Chartink or open local market databases. The renderer validates the bundle's major schema version
before building the weekly, daily, market, sector, recommendation, and TSHA-HBCS pages.

The TSHA-HBCS page is independent of the Chartink bundle. It reads one latest-only
snapshot from the existing `SCANLINKS` KV binding through `GET /api/tsha-hbcs`.
The browser cannot trigger a scan or a write. The local market process replaces
the single snapshot after the India evening run and the US morning run.
Each market/timeframe bucket carries eight completed-period membership bits for
the HT appearance dots. The page retains company names for search and CSV export,
but omits the Name column from the compact table.

Production runs from the public `.github/workflows/refresh.yml` orchestrator. It checks out the
public `routine-systems/market-signals` producer at `main`, creates a fresh bundle, verifies its expected
session when requested, renders the six pages, and deploys that same build to the existing
Cloudflare Pages project.

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
