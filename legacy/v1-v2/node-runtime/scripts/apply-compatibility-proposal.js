const fs = require('fs');
const path = require('path');
const sqlite3 = require('sqlite3').verbose();
const {
  close,
  defaultDbPath,
  findTool,
  get,
  isBlank,
  loadJson,
  normalizePartNumber,
  openDb,
  validateProposal,
} = require('./validate-compatibility-proposal');

const mode = process.argv.includes('--apply') ? 'apply' : 'dry-run';

function usage() {
  return [
    'Usage: node scripts/apply-compatibility-proposal.js <proposal.json> [--apply] [--db docs/db_v2.sqlite]',
    '',
    'Default mode is dry-run. --apply backs up the database and writes validated compatibility claims.',
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

function keyPart(value) {
  return String(value || '').trim().toLowerCase();
}

function sourceKey(source) {
  return [
    source.source_type,
    source.file_path,
    source.title,
  ].filter((part) => !isBlank(part)).map(keyPart).join('|');
}

function claimKey(proposal, accepted, row) {
  return [
    proposal.batch?.catalog_id,
    accepted.subject_public_id,
    row.relationship,
    row.object?.kind,
    row.object?.kind === 'tool'
      ? normalizePartNumber(row.object?.tool_lookup?.part_number || row.object?.value)
      : keyPart(row.object?.value),
    proposal.source?.file_path,
    row.evidence?.page_ref,
    row.evidence?.catalog_page_ref,
    row.evidence?.table_ref,
    row.evidence?.field_ref,
  ].filter((part) => !isBlank(part)).map(keyPart).join('|');
}

function run(db, sql, params = []) {
  return new Promise((resolve, reject) => {
    db.run(sql, params, function onRun(err) {
      if (err) reject(err);
      else resolve(this);
    });
  });
}

function exec(db, sql) {
  return new Promise((resolve, reject) => {
    db.exec(sql, (err) => (err ? reject(err) : resolve()));
  });
}

async function tableExists(db, tableName) {
  const row = await get(db, "SELECT name FROM sqlite_master WHERE type='table' AND name = ?", [tableName]);
  return Boolean(row);
}

async function ensureCompatibilityClaimTables(db) {
  await exec(
    db,
    `CREATE TABLE IF NOT EXISTS compatibility_claims (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      claim_key TEXT NOT NULL UNIQUE,
      subject_tool_id INTEGER NOT NULL REFERENCES catalog_tools(id) ON DELETE CASCADE,
      subject_public_id TEXT NOT NULL,
      subject_part_number TEXT NOT NULL,
      subject_component_type TEXT NOT NULL CHECK (subject_component_type IN ('machine','shank','module','holder','insert','adapter','spare','endmill','drill','reamer','boring_bar','unknown')),
      relationship TEXT NOT NULL CHECK (relationship IN ('mounts_to','accepts_insert','compatible_with_machine','adapts_to','replaces','similar_to')),
      object_kind TEXT NOT NULL CHECK (object_kind IN ('tool','insert_seat','interface','machine_station','unknown')),
      object_tool_id INTEGER REFERENCES catalog_tools(id) ON DELETE CASCADE,
      object_public_id TEXT,
      object_value TEXT NOT NULL,
      object_component_type TEXT NOT NULL CHECK (object_component_type IN ('machine','shank','module','holder','insert','adapter','spare','endmill','drill','reamer','boring_bar','unknown')),
      source_id INTEGER NOT NULL REFERENCES sources(id),
      source_page_ref TEXT,
      source_catalog_page_ref TEXT,
      source_table_ref TEXT,
      source_field_ref TEXT,
      source_raw_text TEXT,
      catalog_id TEXT,
      batch_name TEXT,
      extraction_method TEXT NOT NULL DEFAULT 'manual' CHECK (extraction_method IN ('manual','pdf_table','manufacturer_page','scripted_import','shop_entry')),
      verification_status TEXT NOT NULL DEFAULT 'catalog_claim' CHECK (verification_status IN ('unverified','inferred','catalog_claim','manufacturer_verified','shop_verified','rejected')),
      reviewer TEXT,
      reviewed_at TEXT,
      confidence REAL NOT NULL DEFAULT 0.8 CHECK (confidence >= 0 AND confidence <= 1),
      notes TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_compat_claim_subject ON compatibility_claims(subject_public_id);
    CREATE INDEX IF NOT EXISTS idx_compat_claim_relationship ON compatibility_claims(relationship);
    CREATE INDEX IF NOT EXISTS idx_compat_claim_object ON compatibility_claims(object_kind, object_value);
    CREATE INDEX IF NOT EXISTS idx_compat_claim_source ON compatibility_claims(source_id);
    CREATE INDEX IF NOT EXISTS idx_compat_claim_status ON compatibility_claims(verification_status);`,
  );
  await run(db, "UPDATE schema_meta SET value = '2.2.0' WHERE key = 'schema_version'");
}

async function ensureSource(db, source) {
  const key = sourceKey(source);
  await run(
    db,
    `INSERT OR IGNORE INTO sources
      (source_key, source_type, title, file_name, notes)
      VALUES (?, ?, ?, ?, ?)`,
    [
      key,
      source.source_type,
      clean(source.title),
      clean(source.file_path),
      'Compatibility proposal source.',
    ],
  );
  return get(db, 'SELECT id FROM sources WHERE source_key = ?', [key]);
}

async function objectToolFor(db, row) {
  if (row.object?.kind !== 'tool') return null;
  return findTool(db, row.object.tool_lookup || {});
}

async function insertCompatibilityClaim(db, proposal, accepted) {
  const row = proposal.rows[accepted.row - 1];
  const source = await ensureSource(db, proposal.source || {});
  const objectTool = await objectToolFor(db, row);
  const key = claimKey(proposal, accepted, row);

  const existing = await get(db, 'SELECT id FROM compatibility_claims WHERE claim_key = ?', [key]);
  if (existing) return { id: existing.id, action: 'skipped_existing' };

  const inserted = await run(
    db,
    `INSERT INTO compatibility_claims
      (claim_key, subject_tool_id, subject_public_id, subject_part_number, subject_component_type,
       relationship, object_kind, object_tool_id, object_public_id, object_value, object_component_type,
       source_id, source_page_ref, source_catalog_page_ref, source_table_ref, source_field_ref,
       source_raw_text, catalog_id, batch_name, extraction_method, verification_status, reviewer,
       reviewed_at, confidence, notes)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    [
      key,
      accepted.subject_tool_id,
      accepted.subject_public_id,
      accepted.subject_part_number,
      accepted.subject_component_type || row.subject_lookup?.component_type || 'unknown',
      row.relationship,
      row.object?.kind,
      objectTool?.id || null,
      objectTool?.public_id || null,
      clean(row.object?.value),
      row.object?.component_type || 'unknown',
      source.id,
      clean(row.evidence?.page_ref),
      clean(row.evidence?.catalog_page_ref),
      clean(row.evidence?.table_ref),
      clean(row.evidence?.field_ref),
      clean(row.evidence?.raw_text),
      clean(proposal.batch?.catalog_id),
      clean(proposal.batch?.name),
      clean(row.extraction_method) || 'pdf_table',
      row.verification?.status || 'catalog_claim',
      clean(row.verification?.reviewer),
      clean(row.verification?.reviewed_at),
      typeof row.verification?.confidence === 'number' ? row.verification.confidence : 0.8,
      clean(row.verification?.notes),
    ],
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
  const proposalPath = path.resolve(input);
  const proposal = loadJson(proposalPath);
  if (!fs.existsSync(dbPath)) throw new Error(`Missing database: ${dbPath}`);

  let backup = null;
  if (mode === 'apply') {
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    backup = path.join(path.dirname(dbPath), `${path.basename(dbPath)}.backup-compatibility-${stamp}`);
    fs.copyFileSync(dbPath, backup);
  }

  const db = openDb(dbPath, mode === 'apply' ? sqlite3.OPEN_READWRITE : sqlite3.OPEN_READONLY);
  try {
    const validation = await validateProposal(proposal, db);
    if (!validation.ok) {
      console.log(JSON.stringify({
        mode,
        proposal: proposalPath,
        database: dbPath,
        ok: false,
        issues: validation.issues,
        warnings: validation.warnings,
      }, null, 2));
      process.exitCode = 1;
      return;
    }

    const hadClaimTable = await tableExists(db, 'compatibility_claims');
    const preview = validation.accepted.map((accepted) => ({
      row: accepted.row,
      subject_public_id: accepted.subject_public_id,
      relationship: accepted.relationship,
      object_kind: accepted.object_kind,
      object_value: accepted.object_value,
      status: accepted.status,
      evidence: accepted.evidence,
    }));

    const writeResults = [];
    if (mode === 'apply') {
      await run(db, 'BEGIN TRANSACTION');
      try {
        await ensureCompatibilityClaimTables(db);
        for (const accepted of validation.accepted) {
          writeResults.push(await insertCompatibilityClaim(db, proposal, accepted));
        }
        await run(db, 'COMMIT');
      } catch (err) {
        await run(db, 'ROLLBACK');
        throw err;
      }
    }

    console.log(JSON.stringify({
      mode,
      proposal: proposalPath,
      database: dbPath,
      backup,
      ok: true,
      compatibility_claims_table_present_before_apply: hadClaimTable,
      rows: validation.accepted.length,
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
