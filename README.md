# market-screener-web

Cloudflare Pages presentation for `screener.chiragpatnaik.com`.

This repository accepts one immutable `signals-bundle.v1.json` artifact. It does not scrape
Chartink or open local market databases. The renderer validates the bundle's major schema version
before building the weekly, daily, market, sector, and recommendation pages.

Production runs from the public `.github/workflows/refresh.yml` orchestrator. It checks out the
public `routine-systems/market-signals` producer at `main`, creates a fresh bundle, verifies its expected
session when requested, renders the five pages, and deploys that same build to the existing
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
secret. This repository contains no market database and performs no R2 or D1 writes.
