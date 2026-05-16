const fs = require('fs');
const path = require('path');
const sqlite3 = require('sqlite3').verbose();

const root = path.resolve(__dirname, '..');
const dbPath = path.join(root, 'db.sqlite');
const mode = process.argv.includes('--apply') ? 'apply' : 'dry-run';

const fixes = [
  {
    json_id: 'CCGT21502MRPPS-KCP20S',
    iso_designation: 'CCGT 0602',
    source: 'https://www.kennametal.com/us/en/products/p.topswiss-carbide-insert-positive-right-handed-ccgt-r-pps-medium-machining.7154764.html?pdpQuery=7154764%3Arelevance%3AobsoleteFacet%3Afalse',
    removeSources: [
      'https://www.kennametal.com/us/en/products/p.7154764.html',
    ],
    specUpdates: {
      material_number: '7154764',
      cutting_length_L10: '6.46 mm',
      hole_size_D1: '2.8 mm',
    },
    note: 'Official Kennametal page identifies ISO CCGT060201MRPPS and ANSI CCGT21502MRPPS for material 7154764.',
  },
  {
    json_id: 'CCGT32505MRPPS-KCM25S',
    iso_designation: 'CCGT 09T3',
    source: 'https://s7d2.scene7.com/is/content/Kennametal/final/kennametal/docs/price-lists/kennametal-emea-price-list.pdf',
    specUpdates: {
      material_number: '7154807',
    },
    note: 'Kennametal price list identifies material 7154807 as ISO CCGT09T302MRPPS in grade KCM25S.',
  },
];

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

async function main() {
  if (!fs.existsSync(dbPath)) throw new Error(`Missing database: ${dbPath}`);

  let backup = null;
  if (mode === 'apply') {
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    backup = path.join(root, `db.sqlite.backup-verified-fixes-${stamp}`);
    fs.copyFileSync(dbPath, backup);
  }

  const db = openDb();
  const changes = [];

  for (const fix of fixes) {
    const [row] = await all(db, 'SELECT * FROM tools WHERE json_id = ?', [fix.json_id]);
    if (!row) {
      changes.push({ json_id: fix.json_id, status: 'missing row' });
      continue;
    }

    const specs = parseJson(row.specs, {});
    const sources = parseJson(row.sources, []);
    const nextSpecs = {
      ...specs,
      ...fix.specUpdates,
      verification_notes: [
        ...new Set([...(Array.isArray(specs.verification_notes) ? specs.verification_notes : []), fix.note]),
      ],
    };
    const removeSources = new Set(fix.removeSources || []);
    const nextSources = [...new Set([
      ...(Array.isArray(sources) ? sources : []).filter((source) => !removeSources.has(source)),
      fix.source,
    ])];

    changes.push({
      json_id: fix.json_id,
      before: {
        iso_designation: row.iso_designation,
        specs,
        sources,
      },
      after: {
        iso_designation: fix.iso_designation,
        specs: nextSpecs,
        sources: nextSources,
      },
    });

    if (mode === 'apply') {
      await run(
        db,
        'UPDATE tools SET iso_designation = ?, specs = ?, sources = ? WHERE json_id = ?',
        [fix.iso_designation, JSON.stringify(nextSpecs), JSON.stringify(nextSources), fix.json_id],
      );
    }
  }

  db.close();
  console.log(JSON.stringify({ mode, backup, changes }, null, 2));
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
