# market-screener-web

Cloudflare Pages presentation for `screener.chiragpatnaik.com`.

This repository accepts one immutable `signals-bundle.v1.json` artifact. It does not scrape
Chartink or open local market databases. The renderer validates the bundle's major schema version
before building the weekly, daily, market, sector, and recommendation pages.

## Local build

```bash
./scripts/build tests/fixtures/signals-bundle.v1.json
python3 -m unittest discover -s tests -v
```

The default weekly view is eight weeks. `dist/build-manifest.json` records the input checksum and
producer commit for deployment provenance.

## Deployment boundary

The Pages project remains `screener`. Production cutover is blocked until a preview passes the
acceptance ledger in the `market-system` repository. This repository contains no market database
and performs no R2 or D1 writes.
