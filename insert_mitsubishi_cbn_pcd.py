"""
insert_mitsubishi_cbn_pcd.py — Mitsubishi CBN and PCD turning inserts.

Source: catalogs/Mitsubishi/catalog_c010a_cbn_pcd_inserts.pdf
  Page 39: CBN CCGW/CCGT (CC 80° positive) — SCACR/SCLCR holders + QSM/KM modules (CC size 06, 09T3)
  Page 41: CBN DCGW (DC 55° positive) — SDJCR holders + QSM/KM modules (DC size 07, 11T3)
  Page 42: CBN DCGT w/ breaker — SDJCR holders, size 11T3 only
  Page 43: CBN TCGW (TC 60° positive) — KM16STJCR modules (TC size 11, 16T3 only)
  Page 46: CBN VBGW (VB 35° positive) — KM16SVJBR modules (VB size 11, 16)
  Page 55: PCD DCMT/DCMW — SDJCR holders + QSM modules (DC size 07, 11T3)
  Page 59: PCD VBGT — KM16SVJBR modules (VB size 11)
           PCD VCGT/VCGW — SVJCR holders + QSM-SVJCR modules (VC size 11)

Only inserts that fit holders/modules already in DB are included.
TC size 09 and 13 excluded — no KM module for those sizes in DB.
VC size 08 excluded — no SVJCR holder for size 08 in DB.
All dimensions metric. RE/IC sourced from ISO designation + existing DB records.
LE values converted from catalog inch values (×25.4).
"""

import sqlite3, json

DB = "docs/db.sqlite"
SOURCE_CBN = ("Mitsubishi Materials CBN/PCD Inserts catalog "
              "(catalog_c010a_cbn_pcd_inserts.pdf)")

# ---------------------------------------------------------------------------
# Dimension lookup tables
# ---------------------------------------------------------------------------

# IC (inscribed circle) by shape+size — sourced from existing DB records and
# ISO 1832 standard. Verified against: DCMT-070204 (IC=6.35), DCMT-11T304
# (IC=9.52), VBMT110304 (IC=6.35), VBGT160404 (IC=9.525), TCGT110204 (IC=6.35),
# TCGT16T304 (IC=9.525), VCMT110304 (IC=6.35).
IC_MM = {
    ("CC", "06"):    6.35,
    ("CC", "09T3"):  9.525,
    ("DC", "07"):    6.35,
    ("DC", "11T3"):  9.52,
    ("TC", "11"):    6.35,
    ("TC", "16T3"):  9.525,
    ("VB", "11"):    6.35,
    ("VB", "16"):    9.525,
    ("VC", "11"):    6.35,
}

# Standard thickness by shape+size (mm) — same sourcing
S_MM = {
    ("CC", "06"):    2.38,
    ("CC", "09T3"):  3.97,
    ("DC", "07"):    2.38,
    ("DC", "11T3"):  3.97,
    ("TC", "11"):    2.38,
    ("TC", "16T3"):  3.97,
    ("VB", "11"):    3.18,
    ("VB", "16"):    4.76,
    ("VC", "11"):    3.18,
}

# Corner radius by ISO code suffix
RE_CODE = {
    "V5": 0.05,
    "01": 0.1,
    "02": 0.2,
    "04": 0.4,
    "08": 0.8,
}

# CBN grade descriptions and applicable material groups
# H=Hardened, K=Cast Iron, S=Heat-resistant/Ti, N=Non-ferrous
# Sourced from material-compatibility columns on catalog pages 39-46.
CBN_GRADE_INFO = {
    "SE2":   ("Coated CBN for hardened steel",                    ["H"]),
    "FS2":   ("Coated CBN, fine grain, hardened steel",          ["H"]),
    "FS3":   ("Coated CBN, fine grain, hardened steel",          ["H"]),
    "GS2":   ("Coated CBN, hardened steel + cast iron",         ["H", "K"]),
    "GS3":   ("Coated CBN, hardened steel + cast iron",         ["H", "K"]),
    "GA2":   ("Coated CBN, hardened steel + cast iron",         ["H", "K"]),
    "GH2":   ("Coated CBN, hardened steel, interrupted cut",     ["H"]),
    "VA2":   ("Coated CBN, advanced grade, hardened steel",      ["H"]),
    "TA2":   ("Coated CBN, heat-resistant alloy + titanium",     ["S"]),
    "TH2":   ("Coated CBN, heat-resistant alloy, interrupted",   ["S"]),
    "SE3":   ("Coated CBN for hardened steel",                    ["H"]),
    "SF2":   ("Solid CBN, sintered/special alloy",               ["K"]),
    "SF3":   ("Solid CBN, sintered/special alloy",               ["K"]),
    "FSWS2": ("Coated CBN, wiper geometry, hardened steel",      ["H"]),
    "FBWL2": ("Coated CBN, mirror finish, hardened steel",       ["H"]),
    "GSWS2": ("Coated CBN, wiper, hardened + cast iron",        ["H", "K"]),
    "GAWS2": ("Coated CBN, wiper, hardened + cast iron",        ["H", "K"]),
    "GBWL2": ("Coated CBN, mirror finish, hardened + cast iron",["H", "K"]),
    "TS2":   ("Coated CBN (BF-type), cast iron finishing",       ["K"]),
    # TA2 already defined above (BM-type uses same grade)
}

# PCD grade — all Mitsubishi PCD inserts use grade "DM22" (DCMT/DCMW), or
# are listed without a grade suffix for VBGT/VCGT (all use MD22 PCD grade).
# Per catalog page 55 note. Material: non-ferrous only.
PCD_GRADE_INFO = ("PCD, non-ferrous metals (aluminum, copper, etc.)", ["N"])


# ---------------------------------------------------------------------------
# Raw insert data extracted from catalog pages
# Each tuple: (iso_number, order_number, re_code, le_inch, page, note)
# re_code: V5/01/02/04/08
# le_inch: as string from catalog (for audit trail), converted to mm in build
# ---------------------------------------------------------------------------

CC_CBN = [
    # Page 39 — CCGW size 06, grade SE2 only (fits SCACR-06S, QSM12-SCLCR-06C)
    ("NP-CCGW060202SE2",    "NP-CCGW21.50.5-SE2",  "02", ".067", 39, ""),
    ("NP-CCGW060204SE2",    "NP-CCGW21.51-SE2",    "04", ".071", 39, ""),
    ("NP-CCGW060208SE2",    "NP-CCGW21.52-SE2",    "08", ".079", 39, ""),

    # Page 39 — CCGW size 09T3, multiple grades (fits SCACR-09S, KM16SCLCR0920,
    #            QSM12/16-SCLCR-09C)
    ("NP-CCGW09T302SE2",    "NP-CCGW32.50.5-SE2",   "02", ".067", 39, ""),
    ("NP-CCGW09T304SE2",    "NP-CCGW32.51-SE2",     "04", ".071", 39, ""),
    ("NP-CCGW09T308SE2",    "NP-CCGW32.52-SE2",     "08", ".079", 39, ""),
    ("NP-CCGW09T304FSWS2",  "NP-CCGW32.51-FSWS2",   "04", ".071", 39, "wiper"),
    ("NP-CCGW09T308FSWS2",  "NP-CCGW32.52-FSWS2",   "08", ".079", 39, "wiper"),
    ("NP-CCGW09T304FBWL2",  "NP-CCGW32.51-FBWL2",   "04", ".071", 39, "mirror finish"),
    ("NP-CCGW09T308FBWL2",  "NP-CCGW32.52-FBWL2",   "08", ".079", 39, "mirror finish"),
    ("NP-CCGW09T304GSWS2",  "NP-CCGW32.51-GSWS2",   "04", ".071", 39, "wiper"),
    ("NP-CCGW09T308GSWS2",  "NP-CCGW32.52-GSWS2",   "08", ".079", 39, "wiper"),
    ("NP-CCGW09T304GAWS2",  "NP-CCGW32.51-GAWS2",   "04", ".071", 39, "wiper"),
    ("NP-CCGW09T308GAWS2",  "NP-CCGW32.52-GAWS2",   "08", ".079", 39, "wiper"),
    ("NP-CCGW09T304GBWL2",  "NP-CCGW32.51-GBWL2",   "04", ".071", 39, "mirror finish"),
    ("NP-CCGW09T308GBWL2",  "NP-CCGW32.52-GBWL2",   "08", ".079", 39, "mirror finish"),

    # Page 39 — CCGT w/ breaker, size 09T3 (BF=cast iron, BM=micro-finish)
    ("BF-CCGT09T304TS2",    "BF-CCGT32.51-TS2",     "04", ".071", 39, "with breaker, cast iron"),
    ("BF-CCGT09T308TS2",    "BF-CCGT32.52-TS2",     "08", ".079", 39, "with breaker, cast iron"),
    ("BM-CCGT09T304TA2",    "BM-CCGT32.51-TA2",     "04", ".071", 39, "with breaker, micro-finish"),
    ("BM-CCGT09T308TA2",    "BM-CCGT32.52-TA2",     "08", ".079", 39, "with breaker, micro-finish"),

    # Page 39 — CCGW special IC sizes (marked *2, For SCLC type)
    # Fits: QSM12-SCLCL-09C, QSM16-SCLCL-09C (left-hand SCLC modules)
    # IC 03S (= ~5mm) and 04T0 (= ~6.35mm) — special Mitsubishi sizes
    # These are excluded: non-standard IC, and our SCLCL modules use standard 09 size.
    # If SCLCL modules ever get verified to accept these, add them.
]

DC_CBN = [
    # Page 41 — DCGW size 07 (fits SDJCR-07S holders, QSM12-SDJCR-07C)
    ("NP-DCGW070202FS2",    "NP-DCGW21.50.5-FS2",  "02", ".087", 41, ""),
    ("NP-DCGW070204FS2",    "NP-DCGW21.51-FS2",    "04", ".083", 41, ""),
    ("NP-DCGW070208FS2",    "NP-DCGW21.52-FS2",    "08", ".079", 41, ""),
    ("NP-DCGW070202GS2",    "NP-DCGW21.50.5-GS2",  "02", ".087", 41, ""),
    ("NP-DCGW070204GS2",    "NP-DCGW21.51-GS2",    "04", ".083", 41, ""),
    ("NP-DCGW070208GS2",    "NP-DCGW21.52-GS2",    "08", ".079", 41, ""),
    ("NP-DCGW070202GA2",    "NP-DCGW21.50.5-GA2",  "02", ".087", 41, ""),
    ("NP-DCGW070204GA2",    "NP-DCGW21.51-GA2",    "04", ".083", 41, ""),
    ("NP-DCGW070208GA2",    "NP-DCGW21.52-GA2",    "08", ".079", 41, ""),
    ("NP-DCGW070204TA2",    "NP-DCGW21.51-TA2",    "04", ".083", 41, ""),
    ("NP-DCGW070208TA2",    "NP-DCGW21.52-TA2",    "08", ".079", 41, ""),
    ("NP-DCGW070204SF2",    "NP-DCGW21.51-SF2",    "04", ".083", 41, ""),
    ("NP-DCGW070208SF2",    "NP-DCGW21.52-SF2",    "08", ".079", 41, ""),
    ("NP-DCGW070204SE2",    "NP-DCGW21.51-SE2",    "04", ".083", 41, ""),
    ("NP-DCGW070208SE2",    "NP-DCGW21.52-SE2",    "08", ".079", 41, ""),

    # Page 41 — DCGW size 11T3 (fits SDJCR-11S holders, QSM12/16-SDJCR-11x,
    #             KM16SDJCR1120)
    ("NP-DCGW11T302FS2",    "NP-DCGW32.50.5-FS2",  "02", ".087", 41, ""),
    ("NP-DCGW11T304FS2",    "NP-DCGW32.51-FS2",    "04", ".083", 41, ""),
    ("NP-DCGW11T308FS2",    "NP-DCGW32.52-FS2",    "08", ".079", 41, ""),
    ("NP-DCGW11T304GS2",    "NP-DCGW32.51-GS2",    "04", ".083", 41, ""),
    ("NP-DCGW11T308GS2",    "NP-DCGW32.52-GS2",    "08", ".079", 41, ""),
    ("NP-DCGW11T302GS2",    "NP-DCGW32.50.5-GS2",  "02", ".087", 41, ""),
    ("NP-DCGW11T302GA2",    "NP-DCGW32.50.5-GA2",  "02", ".087", 41, ""),
    ("NP-DCGW11T304GA2",    "NP-DCGW32.51-GA2",    "04", ".083", 41, ""),
    ("NP-DCGW11T308GA2",    "NP-DCGW32.52-GA2",    "08", ".079", 41, ""),
    ("NP-DCGW11T304GH2",    "NP-DCGW32.51-GH2",    "04", ".083", 41, "interrupted"),
    ("NP-DCGW11T308GH2",    "NP-DCGW32.52-GH2",    "08", ".079", 41, "interrupted"),
    ("NP-DCGW11T304VA2",    "NP-DCGW32.51-VA2",    "04", ".083", 41, "new grade"),
    ("NP-DCGW11T308VA2",    "NP-DCGW32.52-VA2",    "08", ".079", 41, "new grade"),
    ("NP-DCGW11T304TA2",    "NP-DCGW32.51-TA2",    "04", ".083", 41, ""),
    ("NP-DCGW11T308TA2",    "NP-DCGW32.52-TA2",    "08", ".079", 41, ""),
    # Note: DC 11T3 TA2 only available in RE=0.4 and RE=0.8 (catalog page 41).
    # No RE=0.2 variant listed — excluded.
    ("NP-DCGW11T304TH2",    "NP-DCGW32.51-TH2",    "04", ".083", 41, "interrupted"),
    ("NP-DCGW11T308TH2",    "NP-DCGW32.52-TH2",    "08", ".079", 41, "interrupted"),
    ("NP-DCGW11T302SF2",    "NP-DCGW32.50.5-SF2",  "02", ".087", 41, ""),
    ("NP-DCGW11T304SF2",    "NP-DCGW32.51-SF2",    "04", ".083", 41, ""),
    ("NP-DCGW11T308SF2",    "NP-DCGW32.52-SF2",    "08", ".079", 41, ""),
    ("NP-DCGW11T302SE2",    "NP-DCGW32.50.5-SE2",  "02", ".087", 41, ""),
    ("NP-DCGW11T304SE2",    "NP-DCGW32.51-SE2",    "04", ".083", 41, ""),
    ("NP-DCGW11T308SE2",    "NP-DCGW32.52-SE2",    "08", ".079", 41, ""),

    # Page 42 — DCGT w/ breaker, size 11T3 (BF=cast iron, BM=micro-finish)
    ("BF-DCGT11T304TS2",    "BF-DCGT32.51-TS2",    "04", ".083", 42, "with breaker, cast iron"),
    ("BF-DCGT11T308TS2",    "BF-DCGT32.52-TS2",    "08", ".079", 42, "with breaker, cast iron"),
    ("BM-DCGT11T304TA2",    "BM-DCGT32.51-TA2",    "04", ".083", 42, "with breaker, micro-finish"),
    ("BM-DCGT11T308TA2",    "BM-DCGT32.52-TA2",    "08", ".079", 42, "with breaker, micro-finish"),
]

TC_CBN = [
    # Page 43 — TCGW size 11 only (fits KM16STJCR1120)
    # TC size 09 and 13 excluded — no module in DB for those sizes.
    ("NP-TCGW110204FS3",    "NP-TCGW21.51-FS3",    "04", ".063", 43, ""),
    ("NP-TCGW110208FS3",    "NP-TCGW21.52-FS3",    "08", ".067", 43, ""),
    ("NP-TCGW110202GS3",    "NP-TCGW21.50.5-GS3",  "02", ".059", 43, ""),
    ("NP-TCGW110204GS3",    "NP-TCGW21.51-GS3",    "04", ".063", 43, ""),
    ("NP-TCGW110208GS3",    "NP-TCGW21.52-GS3",    "08", ".067", 43, ""),
    ("NP-TCGW110204SF3",    "NP-TCGW21.51-SF3",    "04", ".063", 43, ""),
    ("NP-TCGW110208SF3",    "NP-TCGW21.52-SF3",    "08", ".067", 43, ""),
    ("NP-TCGW110204SE3",    "NP-TCGW21.51-SE3",    "04", ".063", 43, ""),
    ("NP-TCGW110208SE3",    "NP-TCGW21.52-SE3",    "08", ".067", 43, ""),

    # Page 43 — TCGW size 16T3 (fits KM16STJCR1620), GS3 grade only
    ("NP-TCGW16T304GS3",    "NP-TCGW32.51-GS3",    "04", ".063", 43, ""),
    ("NP-TCGW16T308GS3",    "NP-TCGW32.52-GS3",    "08", ".067", 43, ""),
]

VB_CBN = [
    # Page 46 — VBGW size 11 (fits KM16SVJBR1120, gage_insert VB..110304)
    ("NP-VBGW110302FS2",    "NP-VBGW220.5-FS2",   "02", ".098", 46, ""),
    ("NP-VBGW110304FS2",    "NP-VBGW221-FS2",     "04", ".098", 46, ""),
    ("NP-VBGW110308FS2",    "NP-VBGW222-FS2",     "08", ".079", 46, ""),
    ("NP-VBGW110302GS2",    "NP-VBGW220.5-GS2",   "02", ".098", 46, ""),
    ("NP-VBGW110304GS2",    "NP-VBGW221-GS2",     "04", ".098", 46, ""),
    ("NP-VBGW110308GS2",    "NP-VBGW222-GS2",     "08", ".079", 46, ""),
    ("NP-VBGW110302GA2",    "NP-VBGW220.5-GA2",   "02", ".098", 46, ""),
    ("NP-VBGW110304GA2",    "NP-VBGW221-GA2",     "04", ".098", 46, ""),
    ("NP-VBGW110308GA2",    "NP-VBGW222-GA2",     "08", ".079", 46, ""),
    ("NP-VBGW110304TA2",    "NP-VBGW221-TA2",     "04", ".098", 46, ""),
    ("NP-VBGW110308TA2",    "NP-VBGW222-TA2",     "08", ".079", 46, ""),
    ("NP-VBGW110304SF2",    "NP-VBGW221-SF2",     "04", ".098", 46, ""),
    ("NP-VBGW110308SF2",    "NP-VBGW222-SF2",     "08", ".079", 46, ""),
    ("NP-VBGW110304SE2",    "NP-VBGW221-SE2",     "04", ".098", 46, ""),
    ("NP-VBGW110308SE2",    "NP-VBGW222-SE2",     "08", ".079", 46, ""),

    # Page 46 — VBGW size 16 (fits KM16SVJBR1630, gage_insert VB..160408)
    ("NP-VBGW160402FS2",    "NP-VBGW330.5-FS2",   "02", ".098", 46, ""),
    ("NP-VBGW160404FS2",    "NP-VBGW331-FS2",     "04", ".098", 46, ""),
    ("NP-VBGW160408FS2",    "NP-VBGW332-FS2",     "08", ".079", 46, ""),
    ("NP-VBGW160402GS2",    "NP-VBGW330.5-GS2",   "02", ".098", 46, ""),
    ("NP-VBGW160404GS2",    "NP-VBGW331-GS2",     "04", ".098", 46, ""),
    ("NP-VBGW160408GS2",    "NP-VBGW332-GS2",     "08", ".079", 46, ""),
    ("NP-VBGW160402GA2",    "NP-VBGW330.5-GA2",   "02", ".098", 46, ""),
    ("NP-VBGW160404GA2",    "NP-VBGW331-GA2",     "04", ".098", 46, ""),
    ("NP-VBGW160408GA2",    "NP-VBGW332-GA2",     "08", ".079", 46, ""),
    ("NP-VBGW160404GH2",    "NP-VBGW331-GH2",     "04", ".098", 46, "interrupted"),
    ("NP-VBGW160408GH2",    "NP-VBGW332-GH2",     "08", ".079", 46, "interrupted"),
    ("NP-VBGW160404VA2",    "NP-VBGW331-VA2",     "04", ".098", 46, "new grade"),
    ("NP-VBGW160408VA2",    "NP-VBGW332-VA2",     "08", ".079", 46, "new grade"),
    ("NP-VBGW160404TA2",    "NP-VBGW331-TA2",     "04", ".098", 46, ""),
    ("NP-VBGW160408TA2",    "NP-VBGW332-TA2",     "08", ".079", 46, ""),
    ("NP-VBGW160404TH2",    "NP-VBGW331-TH2",     "04", ".098", 46, "interrupted"),
    ("NP-VBGW160408TH2",    "NP-VBGW332-TH2",     "08", ".079", 46, "interrupted"),
    ("NP-VBGW160404SF2",    "NP-VBGW331-SF2",     "04", ".098", 46, ""),
    ("NP-VBGW160408SF2",    "NP-VBGW332-SF2",     "08", ".079", 46, ""),
    ("NP-VBGW160404SE2",    "NP-VBGW331-SE2",     "04", ".098", 46, ""),
    ("NP-VBGW160408SE2",    "NP-VBGW332-SE2",     "08", ".079", 46, ""),
]

DC_PCD = [
    # Page 55 — NP-DCMT PCD (with breaker, positive) — fits SDJCR holders
    # Size 07 (fits SDJCR-0808K-07S, SDJCR-1010M-07S, SDJCR-1212K-07S, QSM12-SDJCR-07C)
    ("NP-DCMT070202R-F",    "NP-DCMT21.50.5RF",   "02", ".055", 55, "R-hand PCD"),
    ("NP-DCMT070202L-F",    "NP-DCMT21.50.5LF",   "02", ".055", 55, "L-hand PCD"),
    ("NP-DCMT070204R-F",    "NP-DCMT21.51RF",     "04", ".059", 55, "R-hand PCD"),
    ("NP-DCMT070204L-F",    "NP-DCMT21.51LF",     "04", ".059", 55, "L-hand PCD"),
    # Size 11T3 (fits SDJCR-1010K-11S, SDJCR-1212M-11S, QSM12/16-SDJCR-11x,
    #            KM16SDJCR1120)
    ("NP-DCMT11T302R-F",    "NP-DCMT32.50.5RF",   "02", ".055", 55, "R-hand PCD"),
    ("NP-DCMT11T302L-F",    "NP-DCMT32.50.5LF",   "02", ".055", 55, "L-hand PCD"),
    ("NP-DCMT11T304R-F",    "NP-DCMT32.51RF",     "04", ".059", 55, "R-hand PCD"),
    ("NP-DCMT11T304L-F",    "NP-DCMT32.51LF",     "04", ".059", 55, "L-hand PCD"),

    # Page 55 — DCMW PCD (double-sided, no breaker) — same holders
    # Size 07
    ("DCMW070202",          "DCMW21.50.5",        "02", ".106", 55, "PCD double-sided"),
    ("DCMW070204",          "DCMW21.51",          "04", ".098", 55, "PCD double-sided"),
    # Size 11T3
    ("DCMW11T302",          "DCMW32.50.5",        "02", ".118", 55, "PCD double-sided"),
    ("DCMW11T304",          "DCMW32.51",          "04", ".114", 55, "PCD double-sided"),
]

VB_PCD = [
    # Page 59 — NP-VBGT PCD, size 11 only (fits KM16SVJBR1120)
    # VC size 08 excluded — no holders in DB for that size.
    ("NP-VBGT1103V5R-F",    "NP-VBGT22V5RF",      "V5", ".098", 59, "R-hand PCD, sharp nose"),
    ("NP-VBGT110301R-F",    "NP-VBGT220.2RF",     "01", ".098", 59, "R-hand PCD"),
    ("NP-VBGT110302R-F",    "NP-VBGT220.5RF",     "02", ".098", 59, "R-hand PCD"),
    ("NP-VBGT110304R-F",    "NP-VBGT221RF",       "04", ".098", 59, "R-hand PCD"),
]

VC_PCD = [
    # Page 59 — NP-VCGT PCD, size 11 (fits SVJCR-11S holders, QSM12/16-SVJCR-11C)
    # Size 08 excluded — no holders.
    ("NP-VCGT1103V5R-F",    "NP-VCGT22V5RF",      "V5", ".098", 59, "R-hand PCD, sharp nose"),
    ("NP-VCGT110301R-F",    "NP-VCGT220.2RF",     "01", ".098", 59, "R-hand PCD"),
    ("NP-VCGT110302R-F",    "NP-VCGT220.5RF",     "02", ".098", 59, "R-hand PCD"),
    ("NP-VCGT110304R-F",    "NP-VCGT221RF",       "04", ".098", 59, "R-hand PCD"),

    # Page 59 — VCGW PCD, size 11 (double-sided, same holders)
    ("VCGW110301",          "VCGW220.2",          "01", ".122", 59, "PCD double-sided"),
    ("VCGW110302",          "VCGW220.5",          "02", ".118", 59, "PCD double-sided"),
    ("VCGW110304",          "VCGW221",            "04", ".102", 59, "PCD double-sided"),
]


# ---------------------------------------------------------------------------
# Shape metadata
# ---------------------------------------------------------------------------

SHAPE_META = {
    "CC": ("C (80° Diamond)", "CC turning insert, 7° positive clearance"),
    "DC": ("D (55° Diamond)", "DC turning insert, 7° positive clearance"),
    "TC": ("T (60° Triangle)", "TC turning insert, 7° positive clearance"),
    "VB": ("V (35° Diamond)", "VB turning insert, 5° positive clearance"),
    "VC": ("V (35° Diamond)", "VC turning insert, 7° positive clearance"),
}


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def parse_size(iso_id):
    """Extract (shape_letter, size_code) from an ISO insert designation."""
    # iso_id starts with optional "NP-", "BF-", "BM-" prefix, then shape+size
    # Strip prefixes
    base = iso_id
    for pfx in ("NP-", "BF-", "BM-"):
        if base.startswith(pfx):
            base = base[len(pfx):]
            break
    # First 2 chars = shape (e.g., CC, DC, TC, VB, VC)
    shape2 = base[:2]
    # Next 4 chars = tolerance+type: GW, GT, MT, MW...
    rest = base[4:]  # skip CCGW, DCGW, etc.
    # Extract size code — ends at first digit run or T3
    # Examples: 060202SE2, 09T302SE2, 11T302FS2, 16T304GS3, 070204FS2, 11T302FS2
    import re
    m = re.match(r"(\d{2}(?:T3)?)", rest)
    if m:
        size_code = m.group(1)
    else:
        size_code = rest[:2]
    return shape2, size_code


def grade_from_iso(iso_id):
    """Extract grade suffix from ISO id.

    CBN grade is always the trailing uppercase-leading segment, e.g. SE2, FSWS2.
    Structure after shape code:
      - T3 sizes (09T3, 11T3, 16T3): size + RE_code(2) + grade
      - Non-T3 sizes (06, 07, 11, 16): size + thickness_code(2) + RE_code(2) + grade
    Approach: strip size code, then scan for first uppercase letter — that's
    where the grade starts. Reliable regardless of how many numeric codes precede it.
    """
    import re
    base = iso_id
    for pfx in ("NP-", "BF-", "BM-"):
        if base.startswith(pfx):
            base = base[len(pfx):]
            break
    base = base[4:]          # remove shape (CCGW, DCGW, VBGW, etc.)
    m = re.match(r"\d{2}(?:T3)?", base)
    if m:
        base = base[m.end():]    # remove size code
    # Grade starts at first uppercase letter
    m2 = re.search(r"[A-Z]", base)
    return base[m2.start():] if m2 else base


def build_row(iso_id, order_num, re_code, le_inch_str, page, note, is_pcd):
    import re as re_mod

    shape2, size_code = parse_size(iso_id)
    key = (shape2, size_code)

    ic_mm = IC_MM.get(key)
    s_mm  = S_MM.get(key)
    re_mm = RE_CODE.get(re_code, 0.0)
    le_mm = round(float(le_inch_str) * 25.4, 2)

    if ic_mm is None:
        raise ValueError(f"Unknown IC for shape={shape2} size={size_code} in {iso_id}")

    shape_str, shape_desc = SHAPE_META[shape2]

    if is_pcd:
        grade_desc, mat_groups = PCD_GRADE_INFO
        grade_code = "MD22"  # Mitsubishi standard PCD grade
        category = "CBN/PCD Inserts - PCD"
        material_type = "PCD"
        tags_extra = ["pcd", "non-ferrous", "aluminum"]
    else:
        grade_code = grade_from_iso(iso_id)
        grade_info = CBN_GRADE_INFO.get(grade_code)
        if grade_info is None:
            grade_info = (f"CBN grade {grade_code}", ["H"])
        grade_desc, mat_groups = grade_info
        category = "CBN/PCD Inserts - CBN"
        material_type = "CBN"
        tags_extra = ["cbn", "hardened", "hard turning"]

    # Build description
    note_str = f" ({note})" if note else ""
    desc = (f"Mitsubishi {material_type} {shape2} turning insert. "
            f"ISO: {iso_id}. Grade: {grade_code} — {grade_desc}. "
            f"IC {ic_mm:.3f} mm, RE {re_mm:.2f} mm, LE {le_mm:.2f} mm.{note_str} "
            f"Source: catalog page {page}.")

    specs = {
        "ic_mm":          ic_mm,
        "s_mm":           s_mm,
        "re_mm":          re_mm,
        "le_mm":          le_mm,
        "material_groups": mat_groups,
        "order_number":   order_num,
    }

    tags = (["mitsubishi", "swiss", "turning", shape2, material_type.lower(),
             grade_code, shape2 + size_code.replace("T3", "T3")]
            + tags_extra
            + [m.lower() for m in mat_groups])

    return {
        "json_id":            iso_id,
        "component_type":     "insert",
        "category":           category,
        "type":               f"Mitsubishi {material_type} turning insert",
        "manufacturer":       "Mitsubishi Materials",
        "description":        desc,
        "specs":              json.dumps(specs),
        "size":               size_code,
        "geometry":           None,
        "compatible_machines": None,
        "compatible_inserts": None,
        "sources":            json.dumps([f"{SOURCE_CBN}, page {page}"]),
        "tags":               json.dumps(list(dict.fromkeys(tags))),  # dedup
        "condition":          "New",
        "grade":              grade_code,
        "shape":              shape_str,
        "chipbreaker":        grade_desc,
        "iso_designation":    iso_id,
    }


def build_all_rows():
    rows = []
    for tbl, is_pcd in [
        (CC_CBN,  False),
        (DC_CBN,  False),
        (TC_CBN,  False),
        (VB_CBN,  False),
        (DC_PCD,  True),
        (VB_PCD,  True),
        (VC_PCD,  True),
    ]:
        for entry in tbl:
            iso_id, order_num, re_code, le_inch, page, note = entry
            rows.append(build_row(iso_id, order_num, re_code, le_inch, page, note, is_pcd))
    return rows


def insert_to_db(rows):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    existing = {r[0] for r in c.execute("SELECT json_id FROM tools").fetchall()}
    inserted = skipped = 0
    for row in rows:
        if row["json_id"] in existing:
            skipped += 1
            continue
        c.execute("""
            INSERT INTO tools
            (json_id, component_type, category, type, manufacturer, description,
             specs, size, geometry, compatible_machines, compatible_inserts,
             sources, tags, condition, grade, shape, chipbreaker, iso_designation)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            row["json_id"], row["component_type"], row["category"], row["type"],
            row["manufacturer"], row["description"], row["specs"], row["size"],
            row["geometry"], row["compatible_machines"], row["compatible_inserts"],
            row["sources"], row["tags"], row["condition"], row["grade"],
            row["shape"], row["chipbreaker"], row["iso_designation"],
        ))
        inserted += 1
    conn.commit()
    conn.close()
    return inserted, skipped


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    rows = build_all_rows()
    print(f"Built {len(rows)} records:")
    for r in rows:
        specs = json.loads(r["specs"])
        print(f"  {r['json_id']:<42}  grade={r['grade']:<12}  "
              f"IC={specs['ic_mm']:.3f}  RE={specs['re_mm']:.2f}")

    if "--insert" in sys.argv:
        inserted, skipped = insert_to_db(rows)
        print(f"\nInserted {inserted} new, skipped {skipped} duplicates")
    else:
        print(f"\nRun with --insert to write to database")
