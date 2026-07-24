const fs = require('fs');
const path = require('path');
const sqlite3 = require('sqlite3').verbose();

const root = path.resolve(__dirname, '..', '..');
const defaultDbPath = path.join(root, 'docs', 'db_v2.sqlite');

const allowed = {
  source_type: new Set(['manufacturer_catalog', 'manufacturer_product_page', 'machine_manual', 'shop_note', 'secondary_source', 'unknown']),
  component_type: new Set(['machine', 'shank', 'module', 'holder', 'insert', 'adapter', 'spare', 'endmill', 'drill', 'reamer', 'boring_bar', 'unknown']),
  relationship: new Set(['mounts_to', 'accepts_insert', 'compatible_with_machine', 'adapts_to', 'replaces', 'similar_to']),
  object_kind: new Set(['tool', 'insert_seat', 'interface', 'machine_station', 'unknown']),
  verification_status: new Set(['unverified', 'inferred', 'catalog_claim', 'manufacturer_verified', 'shop_verified', 'rejected']),
};

function openDb(filePath = defaultDbPath, mode = sqlite3.OPEN_READONLY) {
  return new sqlite3.Database(filePath, mode);
}

function get(db, sql, params = []) {
  return new Promise((resolve, reject) => {
    db.get(sql, params, (err, row) => (err ? reject(err) : resolve(row)));
  });
}

function close(db) {
  return new Promise((resolve, reject) => {
    db.close((err) => (err ? reject(err) : resolve()));
  });
}

function argValue(flag) {
  const index = process.argv.indexOf(flag);
  return index >= 0 ? process.argv[index + 1] : null;
}

function proposalArg() {
  const args = process.argv.slice(2);
  return args.filter((arg, index) => !arg.startsWith('--') && args[index - 1] !== '--db')[0] || null;
}

function loadJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8').replace(/^\uFEFF/, ''));
}

function isBlank(value) {
  return value == null || String(value).trim() === '';
}

function normalizePartNumber(value) {
  return String(value || '').replace(/[^A-Z0-9]/gi, '').toUpperCase();
}

function valueAt(object, dottedPath) {
  return dottedPath.split('.').reduce((current, key) => (current == null ? undefined : current[key]), object);
}

function addIssue(issues, row, code, message, evidence = {}) {
  issues.push({ row, code, message, evidence });
}

function requireField(issues, row, object, field) {
  if (isBlank(valueAt(object, field))) addIssue(issues, row, 'missing_required_field', `Missing ${field}.`);
}

function checkEnum(issues, row, object, field, values) {
  const value = valueAt(object, field);
  if (isBlank(value)) {
    addIssue(issues, row, 'missing_required_field', `Missing ${field}.`);
    return;
  }
  if (!values.has(value)) addIssue(issues, row, 'invalid_enum', `Invalid ${field}: ${value}`, { allowed: [...values] });
}

async function findTool(db, lookup) {
  const normalized = normalizePartNumber(lookup.part_number);
  const manufacturer = String(lookup.manufacturer || '').trim().toLowerCase();
  return get(
    db,
    `SELECT t.id, t.public_id, t.part_number, t.tool_kind, s.component_type, m.name AS manufacturer
     FROM catalog_tools t
     LEFT JOIN manufacturers m ON m.id = t.manufacturer_id
     LEFT JOIN swiss_tool_specs s ON s.tool_id = t.id
     WHERE t.normalized_part_number = ?
       AND (? = '' OR lower(m.name) = ? OR lower(m.canonical_name) = ?)
     ORDER BY t.id
     LIMIT 1`,
    [normalized, manufacturer, manufacturer, manufacturer],
  );
}

async function validateProposal(proposal, db) {
  const issues = [];
  const warnings = [];
  const accepted = [];

  if (!proposal || typeof proposal !== 'object' || Array.isArray(proposal)) {
    return { ok: false, issues: [{ row: null, code: 'invalid_root', message: 'Proposal must be a JSON object.', evidence: {} }], warnings, accepted };
  }

  for (const field of ['batch.name', 'batch.catalog_id', 'batch.manufacturer', 'batch.created_at', 'source.file_path', 'source.title']) {
    requireField(issues, null, proposal, field);
  }
  checkEnum(issues, null, proposal, 'source.source_type', allowed.source_type);

  const sourcePath = path.join(root, valueAt(proposal, 'source.file_path') || '');
  if (!fs.existsSync(sourcePath)) addIssue(issues, null, 'missing_source_file', 'Source file does not exist.', { file_path: valueAt(proposal, 'source.file_path') });

  if (!Array.isArray(proposal.rows) || !proposal.rows.length) {
    addIssue(issues, null, 'missing_rows', 'Proposal must include at least one row.');
    return { ok: false, issues, warnings, accepted };
  }

  for (const [index, row] of proposal.rows.entries()) {
    const rowNumber = index + 1;
    for (const field of ['subject_lookup.part_number', 'subject_lookup.manufacturer', 'object.value', 'evidence.page_ref', 'evidence.field_ref', 'verification.status']) {
      requireField(issues, rowNumber, row, field);
    }
    checkEnum(issues, rowNumber, row, 'subject_lookup.component_type', allowed.component_type);
    checkEnum(issues, rowNumber, row, 'relationship', allowed.relationship);
    checkEnum(issues, rowNumber, row, 'object.kind', allowed.object_kind);
    checkEnum(issues, rowNumber, row, 'object.component_type', allowed.component_type);
    checkEnum(issues, rowNumber, row, 'verification.status', allowed.verification_status);

    const subject = await findTool(db, row.subject_lookup || {});
    if (!subject) {
      addIssue(issues, rowNumber, 'subject_not_found', 'Subject tool was not found in v2 catalog.', row.subject_lookup || {});
      continue;
    }
    if (row.subject_lookup.component_type && subject.component_type && row.subject_lookup.component_type !== subject.component_type) {
      addIssue(issues, rowNumber, 'subject_component_type_mismatch', 'Subject component type does not match v2 catalog.', {
        proposal_component_type: row.subject_lookup.component_type,
        database_component_type: subject.component_type,
      });
    }

    if (row.object?.kind === 'tool') {
      const objectTool = await findTool(db, row.object.tool_lookup || {});
      if (!objectTool) addIssue(issues, rowNumber, 'object_tool_not_found', 'Object tool was not found in v2 catalog.', row.object.tool_lookup || {});
    }

    if (row.verification?.status === 'catalog_claim' && row.relationship === 'compatible_with_machine') {
      warnings.push({ row: rowNumber, code: 'machine_compatibility_needs_shop_review', message: 'Machine compatibility should normally stay unverified until Greg/shop verification.' });
    }

    accepted.push({
      row: rowNumber,
      subject_tool_id: subject?.id || null,
      subject_public_id: subject?.public_id || null,
      subject_part_number: subject?.part_number || row.subject_lookup?.part_number,
      subject_component_type: subject?.component_type || row.subject_lookup?.component_type || null,
      relationship: row.relationship,
      object_kind: row.object?.kind,
      object_value: row.object?.value,
      object_component_type: row.object?.component_type || null,
      status: row.verification?.status,
      evidence: `${row.evidence?.page_ref || ''} ${row.evidence?.catalog_page_ref || ''}`.trim(),
    });
  }

  return {
    ok: issues.length === 0,
    issues,
    warnings,
    accepted: issues.length === 0 ? accepted : [],
  };
}

async function main() {
  const input = proposalArg();
  if (!input) {
    console.log('Usage: node scripts/validate-compatibility-proposal.js <proposal.json> [--db docs/db_v2.sqlite]');
    return;
  }

  const dbPath = path.resolve(argValue('--db') || defaultDbPath);
  const proposalPath = path.resolve(input);
  const proposal = loadJson(proposalPath);
  const db = openDb(dbPath);
  try {
    const result = await validateProposal(proposal, db);
    console.log(JSON.stringify({
      proposal: proposalPath,
      database: dbPath,
      ok: result.ok,
      rows: Array.isArray(proposal.rows) ? proposal.rows.length : 0,
      accepted_rows: result.accepted.length,
      issues: result.issues,
      warnings: result.warnings,
      accepted: result.accepted,
    }, null, 2));
    if (!result.ok) process.exitCode = 1;
  } finally {
    await close(db);
  }
}

if (require.main === module) {
  main().catch((err) => {
    console.error(err);
    process.exitCode = 1;
  });
}

module.exports = {
  allowed,
  close,
  defaultDbPath,
  findTool,
  get,
  isBlank,
  loadJson,
  normalizePartNumber,
  openDb,
  root,
  validateProposal,
};
