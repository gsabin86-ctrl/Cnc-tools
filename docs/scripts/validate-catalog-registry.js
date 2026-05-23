const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..', '..');
const defaultRegistryPath = path.join(root, 'docs', 'catalog-registry.json');

const enums = {
  source_type: new Set(['manufacturer_catalog', 'manufacturer_product_page', 'machine_manual', 'shop_note', 'secondary_source', 'unknown']),
  machining_categories: new Set(['turning', 'grooving', 'parting', 'threading', 'boring', 'milling', 'drilling', 'reaming', 'swiss_tooling', 'miniature_tooling', 'cbn_pcd', 'spares', 'general', 'unknown']),
  component_types: new Set(['insert', 'holder', 'module', 'shank', 'adapter', 'bushing', 'spare', 'endmill', 'drill', 'reamer', 'boring_bar', 'threadmill', 'unknown']),
  compatibility_targets: new Set(['accepts_insert', 'mounts_to', 'adapts_to', 'compatible_with_machine', 'replaces', 'similar_to', 'none_known', 'unknown']),
  priority: new Set(['high', 'medium', 'low', 'defer']),
  extraction_status: new Set(['not_started', 'mapped', 'partially_extracted', 'extracted', 'reviewed', 'retired']),
  review_status: new Set(['needs_review', 'approved_scope', 'blocked', 'not_relevant']),
};

function loadJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8').replace(/^\uFEFF/, ''));
}

function addIssue(issues, index, code, message, evidence = {}) {
  issues.push({ catalog_index: index, code, message, evidence });
}

function validateArrayEnum(issues, catalog, index, field) {
  const values = catalog[field];
  if (!Array.isArray(values) || !values.length) {
    addIssue(issues, index, 'missing_array', `${field} must be a non-empty array.`);
    return;
  }
  for (const value of values) {
    if (!enums[field].has(value)) {
      addIssue(issues, index, 'invalid_enum', `Invalid ${field} value: ${value}`, { catalog_id: catalog.catalog_id });
    }
  }
}

function main() {
  const registryPath = path.resolve(process.argv[2] || defaultRegistryPath);
  const registry = loadJson(registryPath);
  const issues = [];
  const warnings = [];

  if (!registry || typeof registry !== 'object' || Array.isArray(registry)) {
    throw new Error('Registry root must be a JSON object.');
  }
  if (!Array.isArray(registry.catalogs)) throw new Error('Registry must include catalogs array.');

  const ids = new Set();
  for (const [index, catalog] of registry.catalogs.entries()) {
    for (const field of ['catalog_id', 'manufacturer', 'title', 'file_path', 'source_type', 'priority', 'extraction_status', 'review_status']) {
      if (catalog[field] == null || String(catalog[field]).trim() === '') {
        addIssue(issues, index + 1, 'missing_required_field', `Missing ${field}.`);
      }
    }
    if (ids.has(catalog.catalog_id)) addIssue(issues, index + 1, 'duplicate_catalog_id', 'Duplicate catalog_id.', { catalog_id: catalog.catalog_id });
    ids.add(catalog.catalog_id);

    for (const field of ['source_type', 'priority', 'extraction_status', 'review_status']) {
      if (catalog[field] && !enums[field].has(catalog[field])) {
        addIssue(issues, index + 1, 'invalid_enum', `Invalid ${field}: ${catalog[field]}`, { catalog_id: catalog.catalog_id });
      }
    }

    validateArrayEnum(issues, catalog, index + 1, 'machining_categories');
    validateArrayEnum(issues, catalog, index + 1, 'component_types');
    validateArrayEnum(issues, catalog, index + 1, 'compatibility_targets');

    const sourcePath = path.join(root, catalog.file_path || '');
    if (!fs.existsSync(sourcePath)) {
      addIssue(issues, index + 1, 'missing_source_file', 'Catalog source file does not exist.', { file_path: catalog.file_path });
    }
    if (catalog.component_types?.includes('unknown') || catalog.machining_categories?.includes('unknown')) {
      warnings.push({ catalog_index: index + 1, code: 'needs_manual_classification', catalog_id: catalog.catalog_id });
    }
  }

  const report = {
    registry: registryPath,
    catalogs: registry.catalogs.length,
    ok: issues.length === 0,
    issues,
    warnings,
  };

  console.log(JSON.stringify(report, null, 2));
  if (issues.length) process.exitCode = 1;
}

main();
