const fs = require('fs');
const path = require('path');
const sqlite3 = require('sqlite3').verbose();
const {
  close,
  defaultDbPath,
  exec,
  get,
  isBlank,
  loadProposal,
  openDb,
  run,
  sourceKey,
  validateProposal,
} = require('./cutting-data-common');

const mode = process.argv.includes('--apply') ? 'apply' : 'dry-run';

function usage() {
  return [
    'Usage: node scripts/apply-cutting-data.js <proposal.json> [--apply] [--db path/to/db_v2.sqlite]',
    '',
    'Default mode is dry-run. --apply backs up the database and writes validated rows.',
  ].join('\n');
}

function argValue(flag) {
  const index = process.argv.indexOf(flag);
  return index >= 0 ? process.argv[index + 1] : null;
}

function proposalArg() {
  const args = process.argv.slice(2);
  return args.filter((arg, index) => !arg.startsWith('--') && args[index - 1] !== '--db')[0] || null;
}

function clean(value) {
  return isBlank(value) ? null : String(value).trim();
}

function numberOrNull(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

async function tableExists(db, tableName) {
  const row = await get(db, "SELECT name FROM sqlite_master WHERE type='table' AND name = ?", [tableName]);
  return Boolean(row);
}

async function ensureCuttingDataTables(db) {
  await exec(
    db,
    `CREATE TABLE IF NOT EXISTS cutting_data_profiles (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      tool_id INTEGER NOT NULL REFERENCES catalog_tools(id) ON DELETE CASCADE,
      source_id INTEGER NOT NULL REFERENCES sources(id),
      source_part_number TEXT NOT NULL,
      source_grade TEXT,
      source_geometry TEXT,
      source_chipbreaker TEXT,
      source_material_label TEXT,
      iso_material_group TEXT NOT NULL CHECK (iso_material_group IN ('P','M','K','N','S','H','O','unknown')),
      material_subgroup TEXT,
      operation_type TEXT NOT NULL DEFAULT 'turning' CHECK (operation_type IN ('turning','boring','grooving','parting','threading','drilling','milling','unknown')),
      cut_condition TEXT CHECK (cut_condition IN ('finishing','medium','roughing','general','unknown')),
      coolant_condition TEXT CHECK (coolant_condition IN ('dry','flood','high_pressure','mql','unknown')),
      surface_speed_min REAL,
      surface_speed_max REAL,
      surface_speed_unit TEXT CHECK (surface_speed_unit IN ('sfm','m_per_min')),
      feed_min REAL,
      feed_max REAL,
      feed_unit TEXT CHECK (feed_unit IN ('ipr','mm_per_rev','ipt','mm_per_tooth','mm_per_min')),
      depth_of_cut_min REAL,
      depth_of_cut_max REAL,
      depth_of_cut_unit TEXT CHECK (depth_of_cut_unit IN ('in','mm')),
      source_page_ref TEXT,
      source_table_ref TEXT,
      extraction_method TEXT NOT NULL DEFAULT 'manual' CHECK (extraction_method IN ('manual','pdf_table','manufacturer_page','scripted_import','shop_entry')),
      verification_status TEXT NOT NULL DEFAULT 'proposed' CHECK (verification_status IN ('proposed','source_extracted','needs_review','catalog_verified','manufacturer_verified','shop_verified','rejected')),
      reviewer TEXT,
      reviewed_at TEXT,
      notes TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      CHECK (surface_speed_min IS NULL OR surface_speed_max IS NULL OR surface_speed_min <= surface_speed_max),
      CHECK (feed_min IS NULL OR feed_max IS NULL OR feed_min <= feed_max),
      CHECK (depth_of_cut_min IS NULL OR depth_of_cut_max IS NULL OR depth_of_cut_min <= depth_of_cut_max)
    );

    CREATE INDEX IF NOT EXISTS idx_cutting_data_tool ON cutting_data_profiles(tool_id);
    CREATE INDEX IF NOT EXISTS idx_cutting_data_source ON cutting_data_profiles(source_id);
    CREATE INDEX IF NOT EXISTS idx_cutting_data_material ON cutting_data_profiles(iso_material_group, material_subgroup);
    CREATE INDEX IF NOT EXISTS idx_cutting_data_operation ON cutting_data_profiles(operation_type);
    CREATE INDEX IF NOT EXISTS idx_cutting_data_status ON cutting_data_profiles(verification_status);

    CREATE TABLE IF NOT EXISTS cutting_data_profile_sources (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      cutting_data_profile_id INTEGER NOT NULL REFERENCES cutting_data_profiles(id) ON DELETE CASCADE,
      source_id INTEGER NOT NULL REFERENCES sources(id),
      evidence_role TEXT NOT NULL DEFAULT 'primary_source' CHECK (evidence_role IN ('primary_source','supporting_source','conversion_check','review_source','rejection_source')),
      evidence_note TEXT,
      UNIQUE(cutting_data_profile_id, source_id, evidence_role)
    );`,
  );
}

async function ensureSource(db, source) {
  const key = sourceKey(source);
  await run(
    db,
    `INSERT OR IGNORE INTO sources
      (source_key, source_type, title, url, file_name, page_ref, notes)
      VALUES (?, ?, ?, ?, ?, ?, ?)`,
    [
      key,
      source.source_type,
      clean(source.title),
      clean(source.url),
      clean(source.file_name),
      clean(source.page_ref),
      clean(source.table_ref ? `Table: ${source.table_ref}` : null),
    ],
  );
  return get(db, 'SELECT id FROM sources WHERE source_key = ?', [key]);
}

async function insertCuttingDataRow(db, accepted) {
  const { row, tool } = accepted;
  const source = await ensureSource(db, row.source);
  const cutting = row.cutting_data || {};
  const verification = row.verification || {};
  const match = row.source_match || {};
  const values = {
    source_part_number: clean(match.part_number),
    source_grade: clean(match.grade),
    source_geometry: clean(match.geometry),
    source_chipbreaker: clean(match.chipbreaker),
    source_material_label: clean(match.material_label),
    material_subgroup: clean(cutting.material_subgroup),
    cut_condition: clean(cutting.cut_condition),
    coolant_condition: clean(cutting.coolant_condition),
    surface_speed_min: numberOrNull(cutting.surface_speed?.min),
    surface_speed_max: numberOrNull(cutting.surface_speed?.max),
    feed_min: numberOrNull(cutting.feed?.min),
    feed_max: numberOrNull(cutting.feed?.max),
    depth_of_cut_min: numberOrNull(cutting.depth_of_cut?.min),
    depth_of_cut_max: numberOrNull(cutting.depth_of_cut?.max),
    source_page_ref: clean(row.source.page_ref),
    source_table_ref: clean(row.source.table_ref),
    extraction_method: clean(row.extraction_method) || 'manual',
    verification_status: verification.status || 'proposed',
    reviewer: clean(verification.reviewer),
    reviewed_at: clean(verification.reviewed_at),
    notes: clean(verification.notes),
  };

  const existing = await get(
    db,
    `SELECT id FROM cutting_data_profiles
     WHERE tool_id = ?
       AND source_id = ?
       AND source_part_number = ?
       AND COALESCE(source_grade, '') = COALESCE(?, '')
       AND iso_material_group = ?
       AND operation_type = ?
       AND COALESCE(surface_speed_min, -1) = COALESCE(?, -1)
       AND COALESCE(surface_speed_max, -1) = COALESCE(?, -1)
       AND COALESCE(feed_min, -1) = COALESCE(?, -1)
       AND COALESCE(feed_max, -1) = COALESCE(?, -1)
       AND COALESCE(depth_of_cut_min, -1) = COALESCE(?, -1)
       AND COALESCE(depth_of_cut_max, -1) = COALESCE(?, -1)
     LIMIT 1`,
    [
      tool.id,
      source.id,
      values.source_part_number,
      values.source_grade,
      cutting.iso_material_group,
      cutting.operation_type || 'turning',
      values.surface_speed_min,
      values.surface_speed_max,
      values.feed_min,
      values.feed_max,
      values.depth_of_cut_min,
      values.depth_of_cut_max,
    ],
  );

  if (existing) return { id: existing.id, action: 'skipped_existing' };

  const inserted = await run(
    db,
    `INSERT INTO cutting_data_profiles
      (tool_id, source_id, source_part_number, source_grade, source_geometry, source_chipbreaker,
       source_material_label, iso_material_group, material_subgroup, operation_type, cut_condition,
       coolant_condition, surface_speed_min, surface_speed_max, surface_speed_unit, feed_min, feed_max,
       feed_unit, depth_of_cut_min, depth_of_cut_max, depth_of_cut_unit, source_page_ref,
       source_table_ref, extraction_method, verification_status, reviewer, reviewed_at, notes)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    [
      tool.id,
      source.id,
      values.source_part_number,
      values.source_grade,
      values.source_geometry,
      values.source_chipbreaker,
      values.source_material_label,
      cutting.iso_material_group,
      values.material_subgroup,
      cutting.operation_type || 'turning',
      values.cut_condition,
      values.coolant_condition,
      values.surface_speed_min,
      values.surface_speed_max,
      cutting.surface_speed?.unit,
      values.feed_min,
      values.feed_max,
      cutting.feed?.unit,
      values.depth_of_cut_min,
      values.depth_of_cut_max,
      cutting.depth_of_cut?.unit,
      values.source_page_ref,
      values.source_table_ref,
      values.extraction_method,
      values.verification_status,
      values.reviewer,
      values.reviewed_at,
      values.notes,
    ],
  );

  await run(
    db,
    `INSERT OR IGNORE INTO cutting_data_profile_sources
      (cutting_data_profile_id, source_id, evidence_role, evidence_note)
      VALUES (?, ?, ?, ?)`,
    [inserted.lastID, source.id, 'primary_source', clean(row.source.table_ref)],
  );

  return { id: inserted.lastID, action: 'inserted' };
}

async function main() {
  const input = proposalArg();
  if (!input) {
    console.log(usage());
    return;
  }

  const dbPath = path.resolve(argValue('--db') || defaultDbPath);
  const { absolutePath, proposal } = loadProposal(input);
  if (!fs.existsSync(dbPath)) throw new Error(`Missing database: ${dbPath}`);

  let backup = null;
  if (mode === 'apply') {
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    backup = path.join(path.dirname(dbPath), `${path.basename(dbPath)}.backup-cutting-data-${stamp}`);
    fs.copyFileSync(dbPath, backup);
  }

  const db = openDb(dbPath, sqlite3.OPEN_READWRITE);
  try {
    const validation = await validateProposal(proposal, db);
    if (!validation.ok) {
      console.log(JSON.stringify({
        mode,
        proposal: absolutePath,
        database: dbPath,
        ok: false,
        errors: validation.errors,
        warnings: validation.warnings,
      }, null, 2));
      process.exitCode = 1;
      return;
    }

    const hasCuttingTable = await tableExists(db, 'cutting_data_profiles');
    const preview = validation.acceptedRows.map((accepted) => ({
      row: accepted.rowIndex,
      tool_id: accepted.tool.id,
      public_id: accepted.tool.public_id,
      part_number: accepted.tool.part_number,
      manufacturer: accepted.tool.manufacturer,
      iso_material_group: accepted.row.cutting_data.iso_material_group,
      operation_type: accepted.row.cutting_data.operation_type,
      verification_status: accepted.row.verification.status,
      source: accepted.row.source.title,
    }));

    const writeResults = [];
    if (mode === 'apply') {
      await run(db, 'BEGIN TRANSACTION');
      try {
        await ensureCuttingDataTables(db);
        for (const accepted of validation.acceptedRows) {
          writeResults.push(await insertCuttingDataRow(db, accepted));
        }
        await run(db, 'COMMIT');
      } catch (err) {
        await run(db, 'ROLLBACK');
        throw err;
      }
    }

    console.log(JSON.stringify({
      mode,
      proposal: absolutePath,
      database: dbPath,
      backup,
      ok: true,
      cutting_tables_present_before_apply: hasCuttingTable,
      rows: validation.acceptedRows.length,
      warnings: validation.warnings,
      preview,
      write_results: writeResults,
    }, null, 2));
  } finally {
    await close(db);
  }
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
