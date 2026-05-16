const fs = require('fs');
const path = require('path');
const sqlite3 = require('sqlite3').verbose();

const root = path.resolve(__dirname, '..');
const dbPath = path.join(root, 'db.sqlite');
const mode = process.argv.includes('--apply') ? 'apply' : 'dry-run';

const scalarColumns = [
  'condition',
  'component_type',
  'category',
  'type',
  'manufacturer',
  'size',
  'geometry',
  'insert_seat',
  'iso_designation',
  'price_range',
  'grade',
  'shape',
  'chipbreaker',
];

const knownTagAliases = new Map([
  ['cast-iron', 'cast iron'],
  ['clamping-unit', 'clamping unit'],
  ['ecas20', 'ECAS20'],
  ['face-grooving', 'face grooving'],
  ['horn', 'Horn'],
  ['internal-coolant', 'internal coolant'],
  ['km micro', 'KM Micro'],
  ['km-micro', 'KM Micro'],
  ['s-clamping', 'S-Clamping'],
  ['s-clamping', 'S-Clamping'],
  ['square-shank', 'square shank'],
  ['tungaloy', 'Tungaloy'],
]);

const knownBrands = new Map([
  ['horn', 'Horn'],
  ['iscAR'.toLowerCase(), 'Iscar'],
  ['kennametal', 'Kennametal'],
  ['sandvik', 'Sandvik'],
  ['star', 'Star'],
  ['star micronics', 'Star Micronics'],
  ['tungaloy', 'Tungaloy'],
]);

function openDb() {
  return new sqlite3.Database(dbPath);
}

function all(db, sql, params = []) {
  return new Promise((resolve, reject) => {
    db.all(sql, params, (err, rows) => (err ? reject(err) : resolve(rows)));
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

function parseJson(value, fallback) {
  if (value == null || String(value).trim() === '') return fallback;
  try {
    return JSON.parse(value);
  } catch {
    return fallback;
  }
}

function titleCase(value) {
  return value
    .split(/\s+/)
    .map((word) => (word ? word[0].toUpperCase() + word.slice(1).toLowerCase() : word))
    .join(' ');
}

function trimCell(value) {
  if (value == null) return value;
  return String(value).replace(/\s+/g, ' ').trim();
}

function stripTypePrefix(value) {
  return value.replace(/^type\s+([A-Z0-9][A-Z0-9.+/-]*)$/i, '$1');
}

function normalizeCondition(value) {
  const clean = trimCell(value);
  if (!clean) return value;
  if (/^new$/i.test(clean)) return 'New';
  if (/^used$/i.test(clean)) return 'Used';
  if (/^refurbished$/i.test(clean)) return 'Refurbished';
  return clean;
}

function normalizeScalar(column, value) {
  const clean = trimCell(value);
  if (value == null || clean === '') return value;
  if (column === 'condition') return normalizeCondition(clean);
  if (['shape', 'chipbreaker', 'geometry', 'type', 'category'].includes(column)) return stripTypePrefix(clean);
  return clean;
}

function normalizeTag(value) {
  const clean = stripTypePrefix(trimCell(value));
  if (!clean) return null;

  const spacedKey = clean.replace(/[-_]+/g, ' ').replace(/\s+/g, ' ').trim().toLowerCase();
  const exactKey = clean.toLowerCase();
  if (knownTagAliases.has(exactKey)) return knownTagAliases.get(exactKey);
  if (knownTagAliases.has(spacedKey)) return knownTagAliases.get(spacedKey);
  if (knownBrands.has(spacedKey)) return knownBrands.get(spacedKey);
  return clean;
}

function normalizeTagsJson(value) {
  const tags = parseJson(value, []);
  if (!Array.isArray(tags)) return value;
  const normalized = [];
  const seen = new Set();
  for (const tag of tags) {
    const next = normalizeTag(tag);
    if (!next) continue;
    const key = next.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    normalized.push(next);
  }
  return JSON.stringify(normalized);
}

function normalizedTagsChanged(value) {
  const tags = parseJson(value, []);
  if (!Array.isArray(tags)) return { changed: false, value };
  const normalized = JSON.parse(normalizeTagsJson(value));
  const sameLength = tags.length === normalized.length;
  const sameValues = sameLength && tags.every((tag, index) => tag === normalized[index]);
  return {
    changed: !sameValues,
    value: JSON.stringify(normalized),
  };
}

function canonical(value) {
  return trimCell(value)
    .replace(/^type\s+([A-Z0-9][A-Z0-9.+/-]*)$/i, '$1')
    .replace(/[-_]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .toUpperCase();
}

function findClusters(rows) {
  const result = {};

  for (const column of scalarColumns) {
    const values = new Map();
    for (const row of rows) {
      const original = row[column];
      if (original == null || String(original).trim() === '') continue;
      const key = canonical(original);
      if (!values.has(key)) values.set(key, new Map());
      values.get(key).set(original, (values.get(key).get(original) || 0) + 1);
    }
    const clusters = [...values]
      .filter(([, variants]) => variants.size > 1)
      .map(([key, variants]) => ({
        key,
        variants: [...variants]
          .sort((a, b) => b[1] - a[1])
          .map(([value, count]) => ({ value, count })),
      }));
    if (clusters.length) result[column] = clusters;
  }

  const tagValues = new Map();
  for (const row of rows) {
    const tags = parseJson(row.tags, []);
    if (!Array.isArray(tags)) continue;
    for (const tag of tags) {
      const key = canonical(tag);
      if (!tagValues.has(key)) tagValues.set(key, new Map());
      tagValues.get(key).set(tag, (tagValues.get(key).get(tag) || 0) + 1);
    }
  }
  const tagClusters = [...tagValues]
    .filter(([, variants]) => variants.size > 1)
    .map(([key, variants]) => ({
      key,
      variants: [...variants]
        .sort((a, b) => b[1] - a[1])
        .map(([value, count]) => ({ value, count })),
    }));
  if (tagClusters.length) result.tags = tagClusters;

  return result;
}

async function audit(db) {
  const rows = await all(db, 'SELECT * FROM tools ORDER BY id');
  return {
    rows: rows.length,
    duplicate_clusters: findClusters(rows),
  };
}

async function main() {
  if (!fs.existsSync(dbPath)) throw new Error(`Missing database: ${dbPath}`);

  let backup = null;
  if (mode === 'apply') {
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    backup = path.join(root, `db.sqlite.backup-normalize-${stamp}`);
    fs.copyFileSync(dbPath, backup);
  }

  const db = openDb();
  const before = await audit(db);
  const rows = await all(db, 'SELECT * FROM tools ORDER BY id');
  const changes = [];

  for (const row of rows) {
    const next = {};
    for (const column of scalarColumns) {
      const value = row[column];
      const normalized = normalizeScalar(column, value);
      if (normalized !== value) next[column] = normalized;
    }

    const tagChange = normalizedTagsChanged(row.tags);
    if (tagChange.changed) next.tags = tagChange.value;

    const changed = Object.keys(next).filter((column) => next[column] !== row[column]);
    if (!changed.length) continue;
    changes.push({ json_id: row.json_id, changed });

    if (mode === 'apply') {
      const assignments = changed.map((column) => `${column} = ?`).join(', ');
      const params = changed.map((column) => next[column]);
      params.push(row.id);
      await run(db, `UPDATE tools SET ${assignments} WHERE id = ?`, params);
    }
  }

  const after = mode === 'apply' ? await audit(db) : null;
  db.close();

  console.log(JSON.stringify({
    mode,
    backup,
    before,
    changes: changes.length,
    change_sample: changes.slice(0, 25),
    after,
  }, null, 2));
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
