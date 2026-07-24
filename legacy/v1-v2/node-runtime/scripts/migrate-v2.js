const fs = require('fs');
const path = require('path');
const sqlite3 = require('sqlite3').verbose();

const root = path.resolve(__dirname, '..');
const sourceDbPath = path.join(root, 'db.sqlite');
const targetDbPath = path.join(root, 'db_v2.sqlite');
const schemaPath = path.join(root, 'db', 'schema-v2.sql');
const mode = process.argv.includes('--apply') ? 'apply' : 'dry-run';

function openDb(filePath) {
  return new sqlite3.Database(filePath);
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

function parseJson(value, fallback) {
  if (value == null || String(value).trim() === '') return fallback;
  try {
    return JSON.parse(value);
  } catch {
    return fallback;
  }
}

function normalizePartNumber(value) {
  return String(value || '').replace(/[^A-Z0-9]/gi, '').toUpperCase();
}

function publicId(value) {
  return String(value || '')
    .trim()
    .replace(/[^A-Za-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .toUpperCase();
}

function sourceKey(source) {
  return String(source || '').trim().toLowerCase();
}

function classifySource(source, manufacturer) {
  const value = String(source || '').trim();
  const lower = value.toLowerCase();
  if (/^https?:\/\//i.test(value)) {
    if (lower.includes('kennametal.com') || lower.includes('iscar.com') || lower.includes('tungaloy.com') || lower.includes('horn') || lower.includes('sandvik')) {
      return 'manufacturer_product_page';
    }
    return 'secondary_source';
  }
  if (/\.pdf/i.test(value) || /catalog/i.test(value)) return 'manufacturer_catalog';
  if (/manual|machine documentation/i.test(value)) return 'machine_manual';
  if (/shop/i.test(value)) return 'shop_note';
  if (manufacturer === 'Generic') return 'unknown';
  return 'unknown';
}

function categorySlugFor(row) {
  if (row.component_type === 'machine') return 'machine';
  if (row.component_type === 'adapter') return 'adapter';
  if (row.component_type === 'spare') return 'spare';
  return 'swiss-tooling';
}

function verificationStatusFor(row) {
  const sources = parseJson(row.sources, []);
  if (!Array.isArray(sources) || sources.length === 0) return 'unverified';
  if (sources.some((source) => /^https?:\/\//i.test(source) && /kennametal|iscar|tungaloy|horn|sandvik/i.test(source))) {
    return 'manufacturer_verified';
  }
  return 'catalog_claim';
}

function stringifySpecValue(value) {
  if (value == null) return null;
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function numberFromValue(value) {
  if (typeof value === 'number') return value;
  const match = String(value || '').match(/-?\d+(?:\.\d+)?/);
  return match ? Number(match[0]) : null;
}

async function insertCategory(db, slug, name, parentSlug = null, description = '', sortOrder = 0) {
  let parentId = null;
  if (parentSlug) {
    const parent = await get(db, 'SELECT id FROM tool_categories WHERE slug = ?', [parentSlug]);
    parentId = parent?.id || null;
  }
  await run(db, 'INSERT OR IGNORE INTO tool_categories (slug, name, parent_id, description, sort_order) VALUES (?, ?, ?, ?, ?)', [
    slug,
    name,
    parentId,
    description,
    sortOrder,
  ]);
}

async function seedCategories(db) {
  await insertCategory(db, 'swiss-tooling', 'Swiss Tooling', null, 'Swiss lathe holders, modules, inserts, adapters, and related tooling.', 10);
  await insertCategory(db, 'solid-carbide', 'Solid Carbide', null, 'Solid carbide mills, drills, reamers, threadmills, and similar round tools.', 20);
  await insertCategory(db, 'endmills', 'Endmills', 'solid-carbide', 'Solid carbide endmills.', 21);
  await insertCategory(db, 'drills', 'Drills', 'solid-carbide', 'Solid carbide drills.', 22);
  await insertCategory(db, 'machine', 'Machines', null, 'Machines and machine tooling platforms.', 90);
  await insertCategory(db, 'adapter', 'Adapters', 'swiss-tooling', 'Adapters and bushings.', 91);
  await insertCategory(db, 'spare', 'Spares', null, 'Replacement parts and spare components.', 92);
}

async function ensureManufacturer(db, name) {
  const clean = name || 'Unknown';
  await run(db, 'INSERT OR IGNORE INTO manufacturers (name, canonical_name) VALUES (?, ?)', [clean, clean]);
  return get(db, 'SELECT id FROM manufacturers WHERE name = ?', [clean]);
}

async function ensureSource(db, source, manufacturerId, manufacturerName) {
  const clean = String(source || '').trim();
  if (!clean) return null;
  const key = sourceKey(clean);
  const isUrl = /^https?:\/\//i.test(clean);
  let title = clean;
  let url = null;
  let fileName = null;
  let pageRef = null;

  if (isUrl) {
    url = clean;
    title = clean;
  } else {
    const pageMatch = clean.match(/\b(p(?:age)?\.?\s*\d+(?:-\d+)?|page\s*\d+(?:-\d+)?)\b/i);
    pageRef = pageMatch ? pageMatch[0] : null;
    const fileMatch = clean.match(/([A-Za-z0-9_. -]+\.pdf)/i);
    fileName = fileMatch ? fileMatch[1].trim() : null;
  }

  await run(
    db,
    `INSERT OR IGNORE INTO sources
      (source_key, source_type, title, url, file_name, page_ref, manufacturer_id)
      VALUES (?, ?, ?, ?, ?, ?, ?)`,
    [key, classifySource(clean, manufacturerName), title, url, fileName, pageRef, manufacturerId],
  );
  return get(db, 'SELECT id FROM sources WHERE source_key = ?', [key]);
}

async function migrate() {
  if (!fs.existsSync(sourceDbPath)) throw new Error(`Missing source DB: ${sourceDbPath}`);
  if (!fs.existsSync(schemaPath)) throw new Error(`Missing schema: ${schemaPath}`);

  const sourceDb = openDb(sourceDbPath);
  const tools = await all(sourceDb, 'SELECT * FROM tools ORDER BY id');
  const edges = await all(sourceDb, "SELECT * FROM compatibility_edges ORDER BY id").catch(() => []);
  sourceDb.close();

  const dryRun = {
    source_tools: tools.length,
    source_edges: edges.length,
    target_db: targetDbPath,
    categories_to_seed: 7,
    manufacturers: new Set(tools.map((row) => row.manufacturer || 'Unknown')).size,
    tool_sources: tools.reduce((count, row) => count + parseJson(row.sources, []).length, 0),
  };

  if (mode !== 'apply') {
    console.log(JSON.stringify({ mode, ...dryRun }, null, 2));
    return;
  }

  if (fs.existsSync(targetDbPath)) {
    throw new Error(`Target already exists: ${targetDbPath}. Move it aside before rerunning.`);
  }

  const targetDb = openDb(targetDbPath);
  await exec(targetDb, fs.readFileSync(schemaPath, 'utf8'));
  await seedCategories(targetDb);

  await run(targetDb, 'BEGIN TRANSACTION');
  try {
    const idByJsonId = new Map();
    const categoryBySlug = new Map((await all(targetDb, 'SELECT slug, id FROM tool_categories')).map((row) => [row.slug, row.id]));

    for (const row of tools) {
      const manufacturer = await ensureManufacturer(targetDb, row.manufacturer);
      const categorySlug = categorySlugFor(row);
      const categoryId = categoryBySlug.get(categorySlug);
      const specs = parseJson(row.specs, {});
      const tags = parseJson(row.tags, []);
      const partNumber = row.json_id;
      const pubId = publicId(row.json_id);
      const verificationStatus = verificationStatusFor(row);
      const searchText = [
        row.json_id,
        row.manufacturer,
        row.component_type,
        row.category,
        row.type,
        row.description,
        row.size,
        row.geometry,
        row.insert_seat,
        row.iso_designation,
        row.grade,
        row.shape,
        row.chipbreaker,
        Array.isArray(tags) ? tags.join(' ') : '',
        JSON.stringify(specs),
      ].filter(Boolean).join(' ');

      const inserted = await run(
        targetDb,
        `INSERT INTO catalog_tools
          (public_id, part_number, normalized_part_number, manufacturer_id, category_id, tool_kind, product_family,
           verification_status, name, description, search_text, source_row_id)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        [
          pubId,
          partNumber,
          normalizePartNumber(partNumber),
          manufacturer.id,
          categoryId,
          row.component_type,
          row.category || row.type || null,
          verificationStatus,
          `${row.manufacturer || 'Unknown'} ${partNumber}`,
          row.description,
          searchText,
          row.id,
        ],
      );
      const toolId = inserted.lastID;
      idByJsonId.set(row.json_id, { id: toolId, public_id: pubId });

      await run(
        targetDb,
        `INSERT INTO swiss_tool_specs
          (tool_id, component_type, mounts_to_public_id, insert_seat, iso_designation, grade, shape, chipbreaker, size, geometry)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        [
          toolId,
          row.component_type,
          row.mounts_to ? publicId(row.mounts_to) : null,
          row.insert_seat,
          row.iso_designation,
          row.grade,
          row.shape,
          row.chipbreaker,
          row.size,
          row.geometry,
        ],
      );

      const aliasRows = [
        ['old_id', row.json_id],
        row.iso_designation ? ['iso', row.iso_designation] : null,
        specs.iso_id ? ['iso', specs.iso_id] : null,
        specs.iso_catalog_id ? ['iso', specs.iso_catalog_id] : null,
        specs.ansi_id ? ['ansi', specs.ansi_id] : null,
        specs.ansi_catalog_id ? ['ansi', specs.ansi_catalog_id] : null,
      ].filter(Boolean);
      for (const [aliasType, alias] of aliasRows) {
        await run(targetDb, 'INSERT OR IGNORE INTO tool_aliases (tool_id, alias, alias_type) VALUES (?, ?, ?)', [toolId, String(alias), aliasType]);
      }

      for (const [key, value] of Object.entries(specs || {})) {
        const valueText = stringifySpecValue(value);
        await run(
          targetDb,
          `INSERT OR IGNORE INTO tool_specs
            (tool_id, spec_key, spec_label, value_text, value_number, value_json, normalized_value, verification_status, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
          [
            toolId,
            key,
            key.replace(/_/g, ' '),
            typeof value === 'object' ? null : valueText,
            numberFromValue(value),
            typeof value === 'object' ? JSON.stringify(value) : null,
            valueText ? valueText.toLowerCase() : null,
            verificationStatus === 'manufacturer_verified' ? 'manufacturer_verified' : 'imported',
            verificationStatus === 'manufacturer_verified' ? 0.85 : 0.55,
          ],
        );
      }

      const sourceIds = [];
      for (const source of parseJson(row.sources, [])) {
        const sourceRow = await ensureSource(targetDb, source, manufacturer.id, row.manufacturer);
        if (!sourceRow) continue;
        sourceIds.push(sourceRow.id);
        await run(
          targetDb,
          'INSERT OR IGNORE INTO tool_sources (tool_id, source_id, evidence_role, verification_status) VALUES (?, ?, ?, ?)',
          [toolId, sourceRow.id, /^https?:\/\//i.test(source) ? 'primary_source' : 'row_source', verificationStatus === 'manufacturer_verified' ? 'manufacturer_verified' : 'catalog_claim'],
        );
      }

      if (sourceIds.length) {
        const specRows = await all(targetDb, 'SELECT id FROM tool_specs WHERE tool_id = ?', [toolId]);
        for (const specRow of specRows) {
          for (const sourceId of sourceIds) {
            await run(targetDb, 'INSERT OR IGNORE INTO tool_spec_sources (tool_spec_id, source_id) VALUES (?, ?)', [specRow.id, sourceId]);
          }
        }
      }

      await run(
        targetDb,
        `INSERT INTO tool_search (rowid, public_id, part_number, manufacturer, category, tool_kind, product_family, description, specs, tags)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        [
          toolId,
          pubId,
          partNumber,
          row.manufacturer || '',
          categorySlug,
          row.component_type,
          row.category || row.type || '',
          row.description || '',
          JSON.stringify(specs || {}),
          Array.isArray(tags) ? tags.join(' ') : '',
        ],
      );
    }

    for (const edge of edges) {
      const subject = idByJsonId.get(edge.subject_json_id);
      const object = idByJsonId.get(edge.object_json_id);
      await run(
        targetDb,
        `INSERT OR IGNORE INTO compatibility_edges
          (edge_key, subject_tool_id, subject_public_id, relationship, object_tool_id, object_public_id,
           verification_status, evidence_kind, confidence, notes, generated_by)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        [
          edge.edge_key,
          subject?.id || null,
          subject?.public_id || publicId(edge.subject_json_id),
          edge.relationship,
          object?.id || null,
          object?.public_id || publicId(edge.object_json_id),
          edge.verification_status === 'needs_review' ? 'unverified' : edge.verification_status,
          edge.evidence_kind || 'existing_database',
          edge.confidence || 0.5,
          edge.notes,
          edge.generated_by || 'migration',
        ],
      );
    }

    await run(targetDb, 'COMMIT');
  } catch (err) {
    await run(targetDb, 'ROLLBACK');
    throw err;
  }

  const counts = {
    catalog_tools: await get(targetDb, 'SELECT COUNT(*) AS count FROM catalog_tools'),
    manufacturers: await get(targetDb, 'SELECT COUNT(*) AS count FROM manufacturers'),
    sources: await get(targetDb, 'SELECT COUNT(*) AS count FROM sources'),
    tool_specs: await get(targetDb, 'SELECT COUNT(*) AS count FROM tool_specs'),
    compatibility_edges: await get(targetDb, 'SELECT COUNT(*) AS count FROM compatibility_edges'),
  };
  const integrity = await all(targetDb, 'PRAGMA integrity_check');
  targetDb.close();

  console.log(JSON.stringify({ mode, target_db: targetDbPath, counts, integrity }, null, 2));
}

migrate().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
