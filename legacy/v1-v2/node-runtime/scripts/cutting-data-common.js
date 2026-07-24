const fs = require('fs');
const path = require('path');
const sqlite3 = require('sqlite3').verbose();

const root = path.resolve(__dirname, '..');
const defaultDbPath = path.join(root, 'db_v2.sqlite');

const allowed = {
  source_type: new Set([
    'manufacturer_product_page',
    'manufacturer_catalog',
    'machine_manual',
    'shop_note',
    'secondary_source',
    'local_file',
    'unknown',
  ]),
  iso_material_group: new Set(['P', 'M', 'K', 'N', 'S', 'H', 'O', 'unknown']),
  operation_type: new Set(['turning', 'boring', 'grooving', 'parting', 'threading', 'drilling', 'milling', 'unknown']),
  cut_condition: new Set(['finishing', 'medium', 'roughing', 'general', 'unknown']),
  coolant_condition: new Set(['dry', 'flood', 'high_pressure', 'mql', 'unknown']),
  surface_speed_unit: new Set(['sfm', 'm_per_min']),
  feed_unit: new Set(['ipr', 'mm_per_rev', 'ipt', 'mm_per_tooth', 'mm_per_min']),
  depth_of_cut_unit: new Set(['in', 'mm']),
  verification_status: new Set([
    'proposed',
    'source_extracted',
    'needs_review',
    'catalog_verified',
    'manufacturer_verified',
    'shop_verified',
    'rejected',
  ]),
  usable_verification_status: new Set(['catalog_verified', 'manufacturer_verified', 'shop_verified']),
};

function openDb(filePath = defaultDbPath, mode = sqlite3.OPEN_READONLY) {
  return new sqlite3.Database(filePath, mode);
}

function all(db, sql, params = []) {
  return new Promise((resolve, reject) => {
    db.all(sql, params, (err, rows) => (err ? reject(err) : resolve(rows)));
  });
}

function get(db, sql, params = []) {
  return new Promise((resolve, reject) => {
    db.get(sql, params, (err, row) => (err ? reject(err) : resolve(row)));
  });
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

function close(db) {
  return new Promise((resolve, reject) => {
    db.close((err) => (err ? reject(err) : resolve()));
  });
}

function valueAt(object, dottedPath) {
  return dottedPath.split('.').reduce((current, key) => (current == null ? undefined : current[key]), object);
}

function isBlank(value) {
  return value == null || String(value).trim() === '';
}

function normalizePartNumber(value) {
  return String(value || '').replace(/[^A-Z0-9]/gi, '').toUpperCase();
}

function loadProposal(filePath) {
  const absolutePath = path.resolve(filePath);
  const proposal = JSON.parse(fs.readFileSync(absolutePath, 'utf8').replace(/^\uFEFF/, ''));
  return { absolutePath, proposal };
}

function sourceKey(source) {
  const parts = [
    source.source_type,
    source.url,
    source.file_name,
    source.page_ref,
    source.table_ref,
    source.title,
  ].filter((part) => !isBlank(part));
  return parts.join('|').trim().toLowerCase();
}

async function findTool(db, lookup) {
  if (!lookup || isBlank(lookup.part_number)) return null;
  const normalized = normalizePartNumber(lookup.part_number);
  const manufacturer = String(lookup.manufacturer || '').trim().toLowerCase();
  return get(
    db,
    `SELECT t.id, t.public_id, t.part_number, t.normalized_part_number, m.name AS manufacturer
     FROM catalog_tools t
     LEFT JOIN manufacturers m ON m.id = t.manufacturer_id
     WHERE t.normalized_part_number = ?
       AND (? = '' OR lower(m.name) = ? OR lower(m.canonical_name) = ?)
     ORDER BY t.id
     LIMIT 1`,
    [normalized, manufacturer, manufacturer, manufacturer],
  );
}

function addError(errors, rowIndex, code, message, evidence = {}) {
  errors.push({ row: rowIndex, code, message, evidence });
}

function addWarning(warnings, rowIndex, code, message, evidence = {}) {
  warnings.push({ row: rowIndex, code, message, evidence });
}

function validateRequired(row, rowIndex, errors, fields) {
  for (const field of fields) {
    if (isBlank(valueAt(row, field))) addError(errors, rowIndex, 'missing_required_field', `Missing required field: ${field}`);
  }
}

function validateEnum(row, rowIndex, errors, field, values, required = true) {
  const value = valueAt(row, field);
  if (isBlank(value)) {
    if (required) addError(errors, rowIndex, 'missing_required_field', `Missing required field: ${field}`);
    return;
  }
  if (!values.has(value)) {
    addError(errors, rowIndex, 'invalid_enum', `Invalid ${field}: ${value}`, { allowed: [...values] });
  }
}

function validateRange(row, rowIndex, errors, prefix, unitField, unitValues) {
  const min = valueAt(row, `${prefix}.min`);
  const max = valueAt(row, `${prefix}.max`);
  const unit = valueAt(row, `${prefix}.unit`);
  const label = prefix.replace('cutting_data.', '');

  if (isBlank(min) && isBlank(max)) {
    addError(errors, rowIndex, 'missing_cutting_range', `Missing ${label} min/max values.`);
  }
  for (const [name, value] of [['min', min], ['max', max]]) {
    if (!isBlank(value) && (typeof value !== 'number' || !Number.isFinite(value) || value < 0)) {
      addError(errors, rowIndex, 'invalid_number', `${label}.${name} must be a non-negative number.`);
    }
  }
  if (typeof min === 'number' && typeof max === 'number' && min > max) {
    addError(errors, rowIndex, 'invalid_range', `${label}.min cannot be greater than ${label}.max.`);
  }
  if (isBlank(unit)) {
    addError(errors, rowIndex, 'missing_required_field', `Missing required field: ${unitField}`);
  } else if (!unitValues.has(unit)) {
    addError(errors, rowIndex, 'invalid_enum', `Invalid ${unitField}: ${unit}`, { allowed: [...unitValues] });
  }
}

function validateSource(row, rowIndex, errors, warnings) {
  const source = row.source || {};
  validateEnum(row, rowIndex, errors, 'source.source_type', allowed.source_type);
  validateRequired(row, rowIndex, errors, ['source.title']);

  const hasUrl = !isBlank(source.url);
  const hasFile = !isBlank(source.file_name);
  if (!hasUrl && !hasFile) {
    addError(errors, rowIndex, 'missing_source_locator', 'Source must include url or file_name.');
  }
  if (hasUrl && !/^https?:\/\//i.test(source.url)) {
    addError(errors, rowIndex, 'invalid_source_url', 'Source url must start with http:// or https://.');
  }
  if (['manufacturer_catalog', 'local_file'].includes(source.source_type) && isBlank(source.page_ref)) {
    addError(errors, rowIndex, 'missing_page_ref', 'Catalog/local-file cutting data must include source.page_ref.');
  }
  if (source.source_type === 'secondary_source') {
    addWarning(warnings, rowIndex, 'secondary_source', 'Secondary source rows should stay needs_review unless no manufacturer source exists.');
  }
}

function validateVerification(row, rowIndex, errors) {
  const verification = row.verification || {};
  validateEnum(row, rowIndex, errors, 'verification.status', allowed.verification_status);

  if (allowed.usable_verification_status.has(verification.status)) {
    validateRequired(row, rowIndex, errors, [
      'verification.reviewer',
      'verification.reviewed_at',
      'source_match.part_number',
      'source_match.grade',
    ]);
  }
}

async function validateProposal(proposal, db) {
  const errors = [];
  const warnings = [];
  const acceptedRows = [];

  if (!proposal || typeof proposal !== 'object' || Array.isArray(proposal)) {
    return { ok: false, errors: [{ row: null, code: 'invalid_root', message: 'Proposal must be a JSON object.' }], warnings, acceptedRows };
  }
  if (!proposal.batch || typeof proposal.batch !== 'object') {
    errors.push({ row: null, code: 'missing_batch', message: 'Proposal is missing batch metadata.' });
  } else {
    for (const field of ['name', 'manufacturer', 'created_at']) {
      if (isBlank(proposal.batch[field])) errors.push({ row: null, code: 'missing_batch_field', message: `Missing batch.${field}.` });
    }
  }
  if (!Array.isArray(proposal.rows) || proposal.rows.length === 0) {
    errors.push({ row: null, code: 'missing_rows', message: 'Proposal must include at least one row.' });
    return { ok: false, errors, warnings, acceptedRows };
  }

  for (const [index, row] of proposal.rows.entries()) {
    const rowIndex = index + 1;
    validateRequired(row, rowIndex, errors, [
      'tool_lookup.part_number',
      'tool_lookup.manufacturer',
      'source_match.part_number',
    ]);
    validateSource(row, rowIndex, errors, warnings);
    validateEnum(row, rowIndex, errors, 'cutting_data.iso_material_group', allowed.iso_material_group);
    validateEnum(row, rowIndex, errors, 'cutting_data.operation_type', allowed.operation_type);
    validateEnum(row, rowIndex, errors, 'cutting_data.cut_condition', allowed.cut_condition, false);
    validateEnum(row, rowIndex, errors, 'cutting_data.coolant_condition', allowed.coolant_condition, false);
    validateRange(row, rowIndex, errors, 'cutting_data.surface_speed', 'cutting_data.surface_speed.unit', allowed.surface_speed_unit);
    validateRange(row, rowIndex, errors, 'cutting_data.feed', 'cutting_data.feed.unit', allowed.feed_unit);
    validateRange(row, rowIndex, errors, 'cutting_data.depth_of_cut', 'cutting_data.depth_of_cut.unit', allowed.depth_of_cut_unit);
    validateVerification(row, rowIndex, errors);

    const tool = await findTool(db, row.tool_lookup || {});
    if (!tool) {
      addError(errors, rowIndex, 'tool_not_found', 'Tool lookup did not match a v2 catalog tool.', row.tool_lookup || {});
      continue;
    }

    const sourcePart = normalizePartNumber(valueAt(row, 'source_match.part_number'));
    if (sourcePart && sourcePart !== tool.normalized_part_number) {
      addError(errors, rowIndex, 'source_part_mismatch', 'source_match.part_number does not match the catalog tool part number.', {
        catalog_part_number: tool.part_number,
        source_part_number: valueAt(row, 'source_match.part_number'),
      });
    }

    acceptedRows.push({ rowIndex, row, tool });
  }

  return {
    ok: errors.length === 0,
    errors,
    warnings,
    acceptedRows: errors.length === 0 ? acceptedRows : [],
  };
}

module.exports = {
  allowed,
  all,
  close,
  defaultDbPath,
  exec,
  get,
  isBlank,
  loadProposal,
  normalizePartNumber,
  openDb,
  root,
  run,
  sourceKey,
  validateProposal,
};
