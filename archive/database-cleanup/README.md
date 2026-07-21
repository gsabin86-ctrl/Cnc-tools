# Database cleanup archive

This directory preserves files removed from the hosted runtime during the first-principles Toolbase rebuild.

- `legacy-root-db.sqlite` is the earlier root database archive.
- `legacy-hosted-index-2026-07-21.html` is the exact pre-promotion `docs/index.html` (SHA-256 `AEF2CB4F19142D129348F31D25E01F53F135939EE94EAFE10A552CD32F8F1504`).

The active static viewer is under `docs/v3/`. The root `docs/index.html` contains only a local redirect to that viewer; it does not load Firebase or the legacy runtime database.
