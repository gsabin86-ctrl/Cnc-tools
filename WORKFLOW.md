# CNC Tool Database — Approved Workflow

**Owner:** Greg Sabin  
**Last updated:** 2026-03-12  
**Status:** LOCKED — do not change without Greg's explicit approval

---

## The Only Way Data Gets Into the Database

```
Source Data → proposals.json → Greg approves → apply_proposals.py → db.sqlite
```

Every single insert must pass through this pipeline. No exceptions.

---

## Step-by-Step

### 1. Source
Pull data from one of:
- Manufacturer catalog PDFs (pdfplumber — no size limit)
- Manufacturer websites (fetch_product.py or manual fetch)
- **Never invent data. Never estimate. Never fill in "typical" values.**

### 2. Propose
Write structured entries to `proposals.json` with `status: "proposed"`.  
Each entry must have:
- `json_id` — exact part number or designation from the source
- `sources` — catalog page reference or URL (required, no exceptions)
- All known fields filled; unknown fields set to `null`

### 3. Audit
Run `python scripts/audit_proposals.py` before presenting to Greg.  
Zero errors required before asking for approval.

### 4. Greg Approves
Present a clear summary of what's proposed.  
**Wait for explicit approval** — "Apply", "Yes", "Approved", or equivalent.  
**Do NOT apply without approval.**

### 5. Apply
Run `python scripts/apply_proposals.py` only after approval.

### 6. Verify
Run `python scripts/audit_db.py` to confirm clean state.

### 7. Backup
Run `scripts/backup_openclaw.ps1` at end of session or when Greg says "save everything" / "good night".

---

## Rules (Non-Negotiable)

| Rule | Detail |
|------|--------|
| No direct DB writes | `db.sqlite` is only touched by `apply_proposals.py` |
| No invented data | Every field must trace to a source document |
| No auto-apply | Greg must explicitly approve every batch before apply |
| Sources required | Every entry needs a `sources` field with catalog page or URL |
| Audit before present | Never show Greg a proposal list that hasn't been audited |
| Batch size | Keep batches to ~20 entries — easier to review |
| **Machine connections require physical verification** | Never set `mounts_to` for a machine station without Greg verifying in person. Catalog specs alone are not sufficient — shank fit, pocket depth, orientation, and coolant ports must be confirmed on the actual machine. Unverified holders stay with `mounts_to=NULL`. |

---

## Known Acceptable Audit Warnings (Do Not Block Apply)

These warnings are expected and do not indicate bad data:

| Entry type | Warning | Why it's OK |
|-----------|---------|-------------|
| Tool holders | `Vague compatible_holders: 'N/A'` | Holders don't go in other holders |
| Spare parts (77–79) | Missing shape/chipbreaker, no manufacturer | Parked intentionally — different category |

---

## Future Automation (Planned — Not Yet Built)

When automation is added (bulk scraping, LM Studio agent loops, etc.), it will:
- Live in a **separate skill** — not this workflow
- Still write to `proposals.json` only
- Still require Greg's approval before apply
- Never bypass this pipeline

This document governs the **manual/catalog workflow** permanently.  
Automation is an addition, not a replacement.

---

## Current Database State (2026-03-12)

| Category | Count | Notes |
|----------|-------|-------|
| Kennametal KM Micro holders | 8 | IDs 68–76 |
| Kennametal/Iscar/Horn inserts | 38 | IDs 1–67, 80–83 |
| KM16 spare parts (parked) | 3 | IDs 77–79 |
| Iscar Swiss holders | 12 | IDs 84–95 |
| Iscar CCMT/DCMT/VCMT inserts | 36 | IDs 96–131 |
| **Total** | **94** | |

---

## Scripts Quick Reference

| Script | When to use |
|--------|------------|
| `scripts/audit_proposals.py` | Before every present-to-Greg |
| `scripts/apply_proposals.py` | After Greg approves |
| `scripts/audit_db.py` | After every apply |
| `scripts/backup_openclaw.ps1` | End of session / "good night" |
| `scripts/fetch_product.py <material_no>` | Fetch Kennametal product page |
| `scripts/write_iscar_proposals.py` | Iscar holders batch 1 |
| `scripts/write_iscar_insert_proposals.py` | Iscar inserts batch 1 |
| `scripts/write_iscar_insert_proposals_2.py` | Iscar inserts batch 2 |
