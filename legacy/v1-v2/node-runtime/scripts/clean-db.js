const fs = require('fs');
const path = require('path');
const sqlite3 = require('sqlite3').verbose();

const root = path.resolve(__dirname, '..');
const dbPath = path.join(root, 'db.sqlite');
const mode = process.argv.includes('--apply') ? 'apply' : 'dry-run';

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

function parseJson(value) {
  if (value == null || String(value).trim() === '') return { ok: true, value: null };
  try {
    return { ok: true, value: JSON.parse(value) };
  } catch (err) {
    return { ok: false, error: err.message };
  }
}

function stringify(value) {
  return JSON.stringify(value);
}

function arrayOrEmpty(value) {
  const parsed = parseJson(value);
  return parsed.ok && Array.isArray(parsed.value) ? parsed.value : [];
}

function objectOrEmpty(value) {
  const parsed = parseJson(value);
  return parsed.ok && parsed.value && typeof parsed.value === 'object' && !Array.isArray(parsed.value)
    ? parsed.value
    : {};
}

function normalizeScalar(value) {
  return String(value || '').trim();
}

function normalizeSources(value) {
  const parsed = parseJson(value);
  if (parsed.ok) {
    if (parsed.value == null) return stringify([]);
    if (Array.isArray(parsed.value)) return stringify(parsed.value.map(normalizeScalar).filter(Boolean));
    return stringify([String(parsed.value)]);
  }
  return stringify([normalizeScalar(value)].filter(Boolean));
}

function normalizeTags(value) {
  const parsed = parseJson(value);
  if (parsed.ok) {
    if (parsed.value == null) return stringify([]);
    if (Array.isArray(parsed.value)) return stringify([...new Set(parsed.value.map(normalizeScalar).filter(Boolean))].sort());
    return stringify([normalizeScalar(parsed.value)].filter(Boolean));
  }
  return stringify([normalizeScalar(value)].filter(Boolean));
}

function normalizeSpecs(value) {
  const parsed = parseJson(value);
  if (parsed.ok) {
    if (parsed.value == null) return stringify({});
    if (parsed.value && typeof parsed.value === 'object' && !Array.isArray(parsed.value)) return stringify(parsed.value);
    return stringify({ value: parsed.value });
  }
  return stringify({ note: normalizeScalar(value) });
}

function normalizeArray(value) {
  const parsed = parseJson(value);
  if (!parsed.ok || parsed.value == null) return stringify([]);
  if (!Array.isArray(parsed.value)) return stringify([normalizeScalar(parsed.value)].filter(Boolean));
  return stringify([...new Set(parsed.value.map(normalizeScalar).filter(Boolean))].sort());
}

function canonicalKey(value) {
  return normalizeScalar(value).replace(/[\s_-]+/g, '').toUpperCase();
}

function isoSeatFromDesignation(value) {
  const clean = canonicalKey(value);
  const match = clean.match(/^([A-Z]{4})(\d{2}[A-Z0-9]{2}|\d{4}|\d{2}T3)/);
  return match ? `${match[1]} ${match[2]}` : null;
}

function idsMatchingSeat(tools, seat) {
  if (!seat) return [];
  const key = canonicalKey(seat);
  return tools
    .filter((tool) => tool.component_type === 'insert' && canonicalKey(tool.iso_designation || tool.json_id).startsWith(key))
    .map((tool) => tool.json_id)
    .sort();
}

function holderIdsForInsert(tools, insert) {
  const seat = insert.iso_designation || isoSeatFromDesignation(insert.json_id);
  if (!seat) return [];
  const seatKey = canonicalKey(seat);
  return tools
    .filter((tool) => ['holder', 'module'].includes(tool.component_type) && canonicalKey(tool.insert_seat).startsWith(seatKey))
    .map((tool) => tool.json_id)
    .sort();
}

function isGenericMachineRef(value) {
  const v = normalizeScalar(value);
  return [
    'Swiss-type CNC lathes',
    'Swiss automatic lathes',
    'Swiss automatic machines',
    'CNC lathes',
    'CNC turning lathes',
    'General CNC lathes',
    'small parts turning centers',
  ].includes(v) || /^CNC lathes\b/i.test(v) || /^Lathes with\b/i.test(v);
}

function knownMachineAlias(value) {
  const v = normalizeScalar(value).toUpperCase().replace(/[^A-Z0-9]/g, '');
  if (v === 'STARECAS20') return 'STAR_ECAS20';
  return null;
}

function addNote(specs, note) {
  if (!note) return specs;
  const notes = Array.isArray(specs.compatibility_notes) ? specs.compatibility_notes : [];
  if (!notes.includes(note)) specs.compatibility_notes = [...notes, note].sort();
  return specs;
}

function cleanMachineRefs(tool, validMachineRefs) {
  const refs = arrayOrEmpty(tool.compatible_machines);
  if (!refs.length) {
    return {
      compatible_machines: tool.compatible_machines,
      specs: tool.specs,
    };
  }
  const specs = objectOrEmpty(tool.specs);
  const cleaned = [];

  for (const ref of refs) {
    const alias = knownMachineAlias(ref);
    if (alias && validMachineRefs.has(alias)) {
      cleaned.push(alias);
      continue;
    }
    if (validMachineRefs.has(ref)) {
      cleaned.push(ref);
      continue;
    }
    if (/^Compatible via holders:/i.test(ref) || isGenericMachineRef(ref)) {
      addNote(specs, ref);
      continue;
    }
    addNote(specs, `Unresolved compatible_machines entry: ${ref}`);
  }

  return {
    compatible_machines: stringify([...new Set(cleaned)].sort()),
    specs: stringify(specs),
  };
}

function cleanInsertRefs(tool, validToolIds, insertIds) {
  const refs = arrayOrEmpty(tool.compatible_inserts);
  if (!refs.length) {
    return {
      compatible_inserts: tool.compatible_inserts,
      specs: tool.specs,
    };
  }
  const specs = objectOrEmpty(tool.specs);
  const cleaned = [];

  for (const ref of refs) {
    const v = normalizeScalar(ref);
    if (!v || /^N\/A\b/i.test(v)) continue;
    if (insertIds.has(v) || validToolIds.has(v)) {
      cleaned.push(v);
      continue;
    }
    if (/^System\b/i.test(v) || / inserts?:/i.test(v)) {
      addNote(specs, v);
      continue;
    }
    addNote(specs, `Unresolved compatible_inserts entry: ${v}`);
  }

  return {
    compatible_inserts: stringify([...new Set(cleaned)].sort()),
    specs: stringify(specs),
  };
}

async function audit(db) {
  const tools = await all(db, 'SELECT * FROM tools ORDER BY id');
  const machines = await all(db, 'SELECT * FROM machines ORDER BY id');
  const validToolIds = new Set(tools.map((tool) => tool.json_id));
  const machineTableIds = machines.map((machine) => machine.json_id);
  const toolMachineIds = tools.filter((tool) => tool.component_type === 'machine').map((tool) => tool.json_id);
  const validMachineRefs = new Set([...machineTableIds, ...toolMachineIds]);
  const insertIds = new Set(tools.filter((tool) => tool.component_type === 'insert').map((tool) => tool.json_id));

  const invalidJson = [];
  for (const tool of tools) {
    for (const col of ['specs', 'compatible_machines', 'compatible_inserts', 'sources', 'tags']) {
      const parsed = parseJson(tool[col]);
      if (!parsed.ok) invalidJson.push({ json_id: tool.json_id, column: col, value: String(tool[col]).slice(0, 90) });
    }
  }

  const brokenMounts = tools.filter((tool) => tool.mounts_to && !validToolIds.has(tool.mounts_to));
  const missingMachineRefs = [];
  const missingInsertRefs = [];

  for (const tool of tools) {
    for (const ref of arrayOrEmpty(tool.compatible_machines)) {
      const alias = knownMachineAlias(ref);
      if (!validMachineRefs.has(ref) && !(alias && validMachineRefs.has(alias))) {
        missingMachineRefs.push({ json_id: tool.json_id, ref });
      }
    }
    for (const ref of arrayOrEmpty(tool.compatible_inserts)) {
      if (!insertIds.has(ref) && !validToolIds.has(ref) && !/^N\/A\b/i.test(ref)) {
        missingInsertRefs.push({ json_id: tool.json_id, ref });
      }
    }
  }

  return {
    rows: tools.length,
    component_counts: tools.reduce((acc, tool) => {
      acc[tool.component_type] = (acc[tool.component_type] || 0) + 1;
      return acc;
    }, {}),
    invalid_json: invalidJson.length,
    invalid_json_sample: invalidJson.slice(0, 12),
    broken_mounts_to: brokenMounts.length,
    missing_machine_refs: missingMachineRefs.length,
    missing_insert_refs: missingInsertRefs.length,
  };
}

async function main() {
  if (!fs.existsSync(dbPath)) throw new Error(`Missing database: ${dbPath}`);

  const db = openDb();
  const backupPath = global.backupPath || null;
  const before = await audit(db);
  const tools = await all(db, 'SELECT * FROM tools ORDER BY id');
  const machines = await all(db, 'SELECT * FROM machines ORDER BY id');
  const validToolIds = new Set(tools.map((tool) => tool.json_id));
  const machineTableIds = machines.map((machine) => machine.json_id);
  const toolMachineIds = tools.filter((tool) => tool.component_type === 'machine').map((tool) => tool.json_id);
  const validMachineRefs = new Set([...machineTableIds, ...toolMachineIds]);
  const insertIds = new Set(tools.filter((tool) => tool.component_type === 'insert').map((tool) => tool.json_id));
  const changes = [];

  for (const tool of tools) {
    const next = {};
    const parsedSpecs = parseJson(tool.specs);
    const parsedSources = parseJson(tool.sources);
    const parsedTags = parseJson(tool.tags);
    const parsedCompatibleMachines = parseJson(tool.compatible_machines);
    const parsedCompatibleInserts = parseJson(tool.compatible_inserts);

    if (!parsedSpecs.ok) next.specs = normalizeSpecs(tool.specs);
    if (!parsedSources.ok) next.sources = normalizeSources(tool.sources);
    if (!parsedTags.ok) next.tags = normalizeTags(tool.tags);
    if (!parsedCompatibleMachines.ok) next.compatible_machines = normalizeArray(tool.compatible_machines);
    if (!parsedCompatibleInserts.ok) next.compatible_inserts = normalizeArray(tool.compatible_inserts);

    const machineClean = cleanMachineRefs({ ...tool, ...next }, validMachineRefs);
    if (machineClean.compatible_machines !== (next.compatible_machines || tool.compatible_machines)) {
      next.compatible_machines = machineClean.compatible_machines;
    }
    if (machineClean.specs !== (next.specs || tool.specs)) next.specs = machineClean.specs;

    const insertClean = cleanInsertRefs({ ...tool, ...next }, validToolIds, insertIds);
    if (insertClean.compatible_inserts !== (next.compatible_inserts || tool.compatible_inserts)) {
      next.compatible_inserts = insertClean.compatible_inserts;
    }
    if (insertClean.specs !== (next.specs || tool.specs)) next.specs = insertClean.specs;

    if (tool.component_type === 'holder' || tool.component_type === 'module') {
      const inserts = idsMatchingSeat(tools, tool.insert_seat);
      if (inserts.length) next.compatible_inserts = stringify(inserts);
    }

    if (tool.component_type === 'insert') {
      const inferredSeat = tool.iso_designation || isoSeatFromDesignation(tool.json_id);
      if (inferredSeat && !tool.iso_designation) next.iso_designation = inferredSeat;
    }

    const changedKeys = Object.keys(next).filter((key) => next[key] !== tool[key]);
    if (!changedKeys.length) continue;
    changes.push({ json_id: tool.json_id, changed: changedKeys });

    if (mode === 'apply') {
      const assignments = changedKeys.map((key) => `${key} = ?`).join(', ');
      const params = changedKeys.map((key) => next[key]);
      params.push(tool.id);
      await run(db, `UPDATE tools SET ${assignments} WHERE id = ?`, params);
    }
  }

  const after = mode === 'apply' ? await audit(db) : null;
  db.close();

  if (mode === 'apply' && changes.length) {
    // The backup is made from the pre-clean snapshot by copying before opening in apply mode.
    // This branch is kept for reporting; the actual copy occurs below in the guarded entrypoint.
  }

  console.log(JSON.stringify({ mode, before, changes: changes.length, change_sample: changes.slice(0, 20), backup: backupPath, after }, null, 2));
}

async function guardedMain() {
  if (mode === 'apply') {
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    const backupPath = path.join(root, `db.sqlite.backup-${stamp}`);
    fs.copyFileSync(dbPath, backupPath);
    global.backupPath = backupPath;
  }
  await main();
}

guardedMain().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
