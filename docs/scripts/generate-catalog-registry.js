const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..', '..');
const catalogsRoot = path.join(root, 'catalogs');
const outputPath = path.join(root, 'docs', 'catalog-registry.json');
const apply = process.argv.includes('--apply');

const manufacturerAliases = [
  ['Sandvik', /sandvik/i],
  ['Iscar', /iscar/i],
  ['Kennametal', /kennametal|topswiss/i],
  ['Mitsubishi', /mitsubishi/i],
  ['PH Horn', /ph horn|horn/i],
  ['Tungaloy', /tungaloy/i],
  ['Sumitomo', /sumitomo|ac5000s/i],
];

function walk(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) return walk(fullPath);
    return [fullPath];
  });
}

function slug(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/\.[^.]+$/, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

function relativePath(filePath) {
  return path.relative(root, filePath).replace(/\\/g, '/');
}

function titleFromFile(filePath) {
  return path.basename(filePath, path.extname(filePath)).replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim();
}

function detectManufacturer(filePath) {
  const rel = relativePath(filePath);
  for (const [name, pattern] of manufacturerAliases) {
    if (pattern.test(rel)) return name;
  }
  return 'Unknown';
}

function addIf(set, condition, value) {
  if (condition) set.add(value);
}

function inferMachiningCategories(text) {
  const lower = text.toLowerCase();
  const categories = new Set();
  addIf(categories, /turn|lathe|nonrotating|externaltoolholder|small_tool|small tools/.test(lower), 'turning');
  addIf(categories, /groov|cuttingoff|cutting-off|parting|corocut/.test(lower), 'grooving');
  addIf(categories, /parting|cuttingoff|cutting-off/.test(lower), 'parting');
  addIf(categories, /thread/.test(lower), 'threading');
  addIf(categories, /boring|internaltoolholder/.test(lower), 'boring');
  addIf(categories, /(?:^|[^a-z])(?:rotating|end ?mill|milling)/.test(lower) && !/nonrotating/.test(lower), 'milling');
  addIf(categories, /drill/.test(lower), 'drilling');
  addIf(categories, /ream/.test(lower), 'reaming');
  addIf(categories, /swiss|langdreh|qs|topswiss|miniature/.test(lower), 'swiss_tooling');
  addIf(categories, /miniature|supermini|mini/.test(lower), 'miniature_tooling');
  addIf(categories, /cbn|pcd/.test(lower), 'cbn_pcd');
  addIf(categories, /spare/.test(lower), 'spares');
  if (!categories.size) categories.add('unknown');
  return [...categories].sort();
}

function inferComponentTypes(text) {
  const lower = text.toLowerCase();
  const types = new Set();
  addIf(types, /insert|coroturn107|corocut|grade/.test(lower), 'insert');
  addIf(types, /holder|toolholder|externaltoolholder|internaltoolholder|nonrotating/.test(lower), 'holder');
  addIf(types, /module|qs/.test(lower), 'module');
  addIf(types, /shank|qs/.test(lower), 'shank');
  addIf(types, /adapter/.test(lower), 'adapter');
  addIf(types, /bushing/.test(lower), 'bushing');
  addIf(types, /spare|screw|clamp|shim/.test(lower), 'spare');
  addIf(types, /(?:^|[^a-z])(?:end ?mill|rotating)/.test(lower) && !/nonrotating/.test(lower), 'endmill');
  addIf(types, /drill/.test(lower), 'drill');
  addIf(types, /ream/.test(lower), 'reamer');
  addIf(types, /boring/.test(lower), 'boring_bar');
  addIf(types, /threadmill/.test(lower), 'threadmill');
  if (!types.size) types.add('unknown');
  return [...types].sort();
}

function inferCompatibilityTargets(componentTypes) {
  const types = new Set(componentTypes);
  const targets = new Set();
  if (types.has('holder') || types.has('boring_bar')) targets.add('accepts_insert');
  if (types.has('module') || types.has('shank') || types.has('holder')) targets.add('mounts_to');
  if (types.has('adapter') || types.has('bushing')) targets.add('adapts_to');
  if (types.has('spare')) targets.add('replaces');
  if (!targets.size) targets.add(types.has('insert') ? 'accepts_insert' : 'unknown');
  return [...targets].sort();
}

function inferPriority(relPath, categories, componentTypes) {
  const text = relPath.toLowerCase();
  if (/split_parts/.test(text)) return 'defer';
  if (categories.includes('swiss_tooling')) return 'high';
  if (componentTypes.includes('insert') && ['turning', 'grooving', 'threading', 'boring'].some((category) => categories.includes(category))) return 'high';
  if (categories.includes('milling') || categories.includes('drilling')) return 'medium';
  return 'medium';
}

function catalogRecord(filePath) {
  const rel = relativePath(filePath);
  const stat = fs.statSync(filePath);
  const manufacturer = detectManufacturer(filePath);
  const title = titleFromFile(filePath);
  const text = `${rel} ${title}`;
  const machiningCategories = inferMachiningCategories(text);
  const componentTypes = inferComponentTypes(text);
  const baseId = `${slug(manufacturer)}-${slug(title)}` || slug(rel);

  return {
    catalog_id: baseId,
    manufacturer,
    title,
    file_path: rel,
    source_type: path.extname(filePath).toLowerCase() === '.pdf' ? 'manufacturer_catalog' : 'unknown',
    catalog_year: (text.match(/\b20\d{2}(?:[-_ ]?20\d{2})?\b/) || [null])[0],
    language: null,
    file_size_bytes: stat.size,
    machining_categories: machiningCategories,
    component_types: componentTypes,
    compatibility_targets: inferCompatibilityTargets(componentTypes),
    priority: inferPriority(rel, machiningCategories, componentTypes),
    extraction_status: 'not_started',
    review_status: 'needs_review',
    notes: 'Auto-generated from filename/path. Needs Greg review before extraction.',
  };
}

function uniqueIds(records) {
  const seen = new Map();
  return records.map((record) => {
    const count = seen.get(record.catalog_id) || 0;
    seen.set(record.catalog_id, count + 1);
    if (!count) return record;
    return { ...record, catalog_id: `${record.catalog_id}-${count + 1}` };
  });
}

function main() {
  if (!fs.existsSync(catalogsRoot)) throw new Error(`Missing catalogs folder: ${catalogsRoot}`);
  const records = uniqueIds(
    walk(catalogsRoot)
      .filter((filePath) => path.extname(filePath).toLowerCase() === '.pdf')
      .sort((a, b) => relativePath(a).localeCompare(relativePath(b)))
      .map(catalogRecord),
  );

  const registry = {
    version: 1,
    generated_at: new Date().toISOString(),
    notes: 'Draft generated from local catalog filenames. Review manufacturer/category/component-type fields before extraction.',
    catalogs: records,
  };

  if (apply) {
    fs.writeFileSync(outputPath, `${JSON.stringify(registry, null, 2)}\n`);
    console.log(`Wrote ${records.length} catalog records to ${outputPath}`);
  } else {
    console.log(JSON.stringify({
      mode: 'dry-run',
      output: outputPath,
      catalogs: records.length,
      by_manufacturer: records.reduce((acc, record) => {
        acc[record.manufacturer] = (acc[record.manufacturer] || 0) + 1;
        return acc;
      }, {}),
      sample: records.slice(0, 10),
    }, null, 2));
  }
}

main();
