# Database Cleanup Log

This log records database-file cleanup decisions so future work does not have to rediscover which SQLite file is real.

## 2026-05-18

### Root `db.sqlite` archived

The root-level `db.sqlite` was identified as a stale legacy database and moved out of the active project root.

| Field | Value |
|-------|-------|
| Original path | `db.sqlite` |
| Archive path | `archive/database-cleanup/legacy-root-db.sqlite` |
| Size | 704,512 bytes |
| Main table | `tools` |
| Row count | 629 |
| SHA256 | `750A42085D17B5A033D0AECD14F0CCA0C6E7C98307CA63D72CA4B9D55885A414` |

Current active databases after cleanup:

| File | Role |
|------|------|
| `docs/db.sqlite` | Current production UI database. |
| `docs/db_v2.sqlite` | Normalized future database. |

The archived root database should not be used for new data work. If something appears to depend on it later, compare it against `docs/db.sqlite` before restoring anything.
