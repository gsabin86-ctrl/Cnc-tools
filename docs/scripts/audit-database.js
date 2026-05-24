const fs = require('fs');
const path = require('path');
const sqlite3 = require('sqlite3').verbose();

const root = path.resolve(__dirname, '..');
const defaultDatabases = ['db.sqlite', 'db_v2.sqlite'];
const args = new Set(process.argv.slice(2));
const jsonOutput = args.has('--json');

function dbPathFor(name) {
  return path.isAbsolute(name) ? name : path.join(root, name);
}

function openDb(filePath) {
  return new sqlite3.Database(filePath, sqlite3.OPEN_READONLY);
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

function close(db) {
  return new Promise((resolve, reject) => {
    db.close((err) => (err ? reject(err) : resolve()));
  });
}

function tryParseJson(value) {
  if (value == null || String(value).trim() === '') return { ok: true, value: null };
  try {
    return { ok: true, value: JSON.parse(value) };
  } catch (err) {
    return { ok: false, error: err.message };
  }
}

function countBy(rows, key) {
  return rows.reduce((acc, row) => {
    const value = row[key] == null || row[key] === '' ? '(blank)' : String(row[key]);
    acc[value] = (acc[value] || 0) + 1;
    return acc;
  }, {});
}

function sortObject(object) {
  return Object.fromEntries(
    Object.entries(object).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])),
  );
}

function addIssue(issues, severity, code, message, evidence = {}) {
  issues.push({ severity, code, message, evidence });
}

function severityRank(severity) {
  return { high: 3, medium: 2, low: 1 }[severity] || 0;
}

function summarizeIssues(issues) {
  return {
    total: issues.length,
    by_severity: sortObject(countBy(issues, 'severity')),
    by_code: sortObject(countBy(issues, 'code')),
    top: issues
      .slice()
      .sort((a, b) => severityRank(b.severity) - severityRank(a.severity) || a.code.localeCompare(b.code))
      .slice(0, 25),
  };
}

async function tableNames(db) {
  const rows = await all(db, "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name");
  return rows.map((row) => row.name);
}

async function auditLegacyTools(db, tables) {
  const issues = [];
  if (!tables.includes('tools')) return null;

  const tools = await all(db, 'SELECT * FROM tools ORDER BY id');
  const duplicates = await all(
    db,
    'SELECT json_id, COUNT(*) AS count FROM tools GROUP BY json_id HAVING COUNT(*) > 1 ORDER BY count DESC, json_id',
  );
  for (const duplicate of duplicates) {
    addIssue(issues, 'high', 'duplicate_json_id', 'Duplicate tool identifier.', duplicate);
  }

  const jsonColumns = ['specs', 'compatible_machines', 'compatible_inserts', 'sources', 'tags'];
  const invalidJson = {};
  for (const column of jsonColumns) invalidJson[column] = [];

  let missingSources = 0;
  let urlSourceRows = 0;
  let compatibleInsertRows = 0;
  let mountRows = 0;
  let textOnlySourceRows = 0;

  for (const tool of tools) {
    for (const column of jsonColumns) {
      const parsed = tryParseJson(tool[column]);
      if (!parsed.ok) invalidJson[column].push(tool.json_id);
    }

    const parsedSources = tryParseJson(tool.sources);
    const sources = parsedSources.ok && Array.isArray(parsedSources.value) ? parsedSources.value : [];
    if (!sources.length && !['machine', 'spare'].includes(tool.component_type)) {
      missingSources += 1;
      addIssue(issues, 'high', 'missing_source', 'Tool has no source.', {
        json_id: tool.json_id,
        component_type: tool.component_type,
      });
    }
    if (sources.some((source) => /^https?:\/\//i.test(String(source)))) urlSourceRows += 1;
    if (sources.length && sources.every((source) => !/^https?:\/\//i.test(String(source)))) {
      textOnlySourceRows += 1;
    }
    if (tool.mounts_to) mountRows += 1;

    const parsedCompatible = tryParseJson(tool.compatible_inserts);
    if (parsedCompatible.ok && Array.isArray(parsedCompatible.value) && parsedCompatible.value.length) {
      compatibleInsertRows += 1;
    }

    if (tool.manufacturer === 'Horn') {
      addIssue(issues, 'low', 'manufacturer_alias', 'Manufacturer uses Horn instead of PH Horn.', {
        json_id: tool.json_id,
      });
    }
  }

  for (const [column, ids] of Object.entries(invalidJson)) {
    if (ids.length) {
      addIssue(issues, 'high', 'invalid_json', `Column ${column} contains invalid JSON.`, {
        column,
        count: ids.length,
        examples: ids.slice(0, 10),
      });
    }
  }

  const componentCounts = await all(
    db,
    'SELECT component_type, COUNT(*) AS count FROM tools GROUP BY component_type ORDER BY count DESC, component_type',
  );
  const manufacturerCounts = await all(
    db,
    'SELECT COALESCE(manufacturer, "(blank)") AS manufacturer, COUNT(*) AS count FROM tools GROUP BY manufacturer ORDER BY count DESC, manufacturer',
  );

  if (tables.includes('compatibility_edges')) {
    const edgeSummary = await all(
      db,
      'SELECT relationship, verification_status, evidence_kind, COUNT(*) AS count FROM compatibility_edges GROUP BY relationship, verification_status, evidence_kind ORDER BY count DESC',
    );
    const unresolvedEdges = await get(
      db,
      `SELECT COUNT(*) AS count
       FROM compatibility_edges e
       LEFT JOIN tools s ON s.json_id = e.subject_json_id
       LEFT JOIN tools o ON o.json_id = e.object_json_id
       WHERE s.json_id IS NULL OR o.json_id IS NULL`,
    );
    if (unresolvedEdges.count) {
      addIssue(issues, 'medium', 'unresolved_compatibility_edge', 'Compatibility edge references a missing tool.', {
        count: unresolvedEdges.count,
      });
    }
    return {
      row_count: tools.length,
      component_counts: componentCounts,
      manufacturer_counts: manufacturerCounts,
      source_coverage: {
        missing_source_rows: missingSources,
        rows_with_url_source: urlSourceRows,
        text_only_source_rows: textOnlySourceRows,
      },
      relationship_coverage: {
        rows_with_mounts_to: mountRows,
        rows_with_compatible_inserts: compatibleInsertRows,
        compatibility_edges: edgeSummary,
        unresolved_edges: unresolvedEdges.count,
      },
      issues: summarizeIssues(issues),
    };
  }

  return {
    row_count: tools.length,
    component_counts: componentCounts,
    manufacturer_counts: manufacturerCounts,
    source_coverage: {
      missing_source_rows: missingSources,
      rows_with_url_source: urlSourceRows,
      text_only_source_rows: textOnlySourceRows,
    },
    relationship_coverage: {
      rows_with_mounts_to: mountRows,
      rows_with_compatible_inserts: compatibleInsertRows,
    },
    issues: summarizeIssues(issues),
  };
}

async function auditV2(db, tables) {
  const issues = [];
  if (!tables.includes('catalog_tools')) return null;

  const toolCount = await get(db, 'SELECT COUNT(*) AS count FROM catalog_tools');
  const sourceCount = tables.includes('sources') ? await get(db, 'SELECT COUNT(*) AS count FROM sources') : { count: 0 };
  const specCount = tables.includes('tool_specs') ? await get(db, 'SELECT COUNT(*) AS count FROM tool_specs') : { count: 0 };
  const edgeCount = tables.includes('compatibility_edges')
    ? await get(db, 'SELECT COUNT(*) AS count FROM compatibility_edges')
    : { count: 0 };
  const compatibilityClaimCount = tables.includes('compatibility_claims')
    ? await get(db, 'SELECT COUNT(*) AS count FROM compatibility_claims')
    : { count: 0 };
  const cuttingDataCount = tables.includes('cutting_data_profiles')
    ? await get(db, 'SELECT COUNT(*) AS count FROM cutting_data_profiles')
    : { count: 0 };

  const verification = await all(
    db,
    'SELECT verification_status, COUNT(*) AS count FROM catalog_tools GROUP BY verification_status ORDER BY count DESC',
  );
  const sourceTypes = tables.includes('sources')
    ? await all(db, 'SELECT source_type, COUNT(*) AS count FROM sources GROUP BY source_type ORDER BY count DESC')
    : [];
  const sourceUrls = tables.includes('sources')
    ? await get(db, "SELECT SUM(CASE WHEN url IS NOT NULL AND url <> '' THEN 1 ELSE 0 END) AS with_url, COUNT(*) AS total FROM sources")
    : { with_url: 0, total: 0 };
  const cuttingDataVerification = tables.includes('cutting_data_profiles')
    ? await all(db, 'SELECT verification_status, COUNT(*) AS count FROM cutting_data_profiles GROUP BY verification_status ORDER BY count DESC')
    : [];

  if (sourceUrls.total && sourceUrls.with_url < sourceUrls.total) {
    addIssue(issues, 'medium', 'sources_without_url', 'Some structured sources do not have URLs.', {
      with_url: sourceUrls.with_url,
      total: sourceUrls.total,
    });
  }

  let edgeSummary = [];
  let unresolvedEdges = { count: 0 };
  let claimSummary = [];
  if (tables.includes('compatibility_edges')) {
    edgeSummary = await all(
      db,
      'SELECT relationship, verification_status, evidence_kind, COUNT(*) AS count FROM compatibility_edges GROUP BY relationship, verification_status, evidence_kind ORDER BY count DESC',
    );
    unresolvedEdges = await get(
      db,
      'SELECT COUNT(*) AS count FROM compatibility_edges WHERE subject_tool_id IS NULL OR object_tool_id IS NULL',
    );
    if (unresolvedEdges.count) {
      addIssue(issues, 'medium', 'unresolved_v2_edge', 'V2 compatibility edge is not linked to both catalog tool rows.', {
        count: unresolvedEdges.count,
      });
    }
  }
  if (tables.includes('compatibility_claims')) {
    claimSummary = await all(
      db,
      'SELECT relationship, object_kind, verification_status, COUNT(*) AS count FROM compatibility_claims GROUP BY relationship, object_kind, verification_status ORDER BY count DESC',
    );
  }

  const unverifiedTools = verification.find((row) => row.verification_status === 'unverified');
  if (unverifiedTools?.count) {
    addIssue(issues, 'high', 'unverified_catalog_tools', 'Some catalog tools are unverified.', {
      count: unverifiedTools.count,
    });
  }

  return {
    catalog_tool_count: toolCount.count,
    source_count: sourceCount.count,
    tool_spec_count: specCount.count,
    compatibility_edge_count: edgeCount.count,
    compatibility_claim_count: compatibilityClaimCount.count,
    cutting_data_count: cuttingDataCount.count,
    verification,
    source_types: sourceTypes,
    source_url_coverage: sourceUrls,
    compatibility_edges: {
      summary: edgeSummary,
      unresolved_edges: unresolvedEdges.count,
    },
    compatibility_claims: {
      summary: claimSummary,
    },
    cutting_data: {
      verification: cuttingDataVerification,
    },
    issues: summarizeIssues(issues),
  };
}

async function auditDatabase(name) {
  const filePath = dbPathFor(name);
  if (!fs.existsSync(filePath)) {
    return {
      database: name,
      path: filePath,
      exists: false,
      issues: summarizeIssues([
        { severity: 'high', code: 'missing_database', message: 'Database file does not exist.', evidence: {} },
      ]),
    };
  }

  const db = openDb(filePath);
  try {
    const tables = await tableNames(db);
    return {
      database: path.basename(filePath),
      path: filePath,
      exists: true,
      bytes: fs.statSync(filePath).size,
      tables,
      legacy_tools: await auditLegacyTools(db, tables),
      v2: await auditV2(db, tables),
    };
  } finally {
    await close(db);
  }
}

function renderTable(title, rows, columns) {
  if (!rows || rows.length === 0) return [];
  const lines = [title];
  for (const row of rows) {
    lines.push(`  ${columns.map((column) => `${column}=${row[column]}`).join(' ')}`);
  }
  return lines;
}

function renderHuman(report) {
  const lines = [`Database audit generated at ${report.generated_at}`];
  for (const dbReport of report.databases) {
    lines.push('', `== ${dbReport.database} ==`);
    if (!dbReport.exists) {
      lines.push('Missing database file.');
      continue;
    }
    lines.push(`Path: ${dbReport.path}`);
    lines.push(`Size: ${dbReport.bytes} bytes`);
    if (dbReport.legacy_tools) {
      const legacy = dbReport.legacy_tools;
      lines.push(`Legacy tools: ${legacy.row_count}`);
      lines.push(`Source coverage: missing=${legacy.source_coverage.missing_source_rows} url_rows=${legacy.source_coverage.rows_with_url_source} text_only_rows=${legacy.source_coverage.text_only_source_rows}`);
      lines.push(`Relationship coverage: mounts_to_rows=${legacy.relationship_coverage.rows_with_mounts_to} compatible_insert_rows=${legacy.relationship_coverage.rows_with_compatible_inserts}`);
      lines.push(...renderTable('Component counts:', legacy.component_counts, ['component_type', 'count']));
      if (legacy.relationship_coverage.compatibility_edges) {
        lines.push(...renderTable('Compatibility edge counts:', legacy.relationship_coverage.compatibility_edges, ['relationship', 'verification_status', 'evidence_kind', 'count']));
      }
      lines.push(`Issues: total=${legacy.issues.total} by_severity=${JSON.stringify(legacy.issues.by_severity)}`);
    }
    if (dbReport.v2) {
      const v2 = dbReport.v2;
      lines.push(`V2 catalog tools: ${v2.catalog_tool_count}`);
      lines.push(`V2 sources: ${v2.source_count} (${v2.source_url_coverage.with_url}/${v2.source_url_coverage.total} with URL)`);
      lines.push(`V2 tool specs: ${v2.tool_spec_count}`);
      lines.push(`V2 compatibility edges: ${v2.compatibility_edge_count} unresolved=${v2.compatibility_edges.unresolved_edges}`);
      lines.push(`V2 compatibility claims: ${v2.compatibility_claim_count}`);
      lines.push(`V2 cutting data profiles: ${v2.cutting_data_count}`);
      lines.push(...renderTable('V2 verification:', v2.verification, ['verification_status', 'count']));
      lines.push(...renderTable('V2 source types:', v2.source_types, ['source_type', 'count']));
      lines.push(...renderTable('V2 compatibility edge counts:', v2.compatibility_edges.summary, ['relationship', 'verification_status', 'evidence_kind', 'count']));
      lines.push(...renderTable('V2 compatibility claim counts:', v2.compatibility_claims.summary, ['relationship', 'object_kind', 'verification_status', 'count']));
      lines.push(...renderTable('V2 cutting data verification:', v2.cutting_data.verification, ['verification_status', 'count']));
      lines.push(`Issues: total=${v2.issues.total} by_severity=${JSON.stringify(v2.issues.by_severity)}`);
    }
  }
  return lines.join('\n');
}

async function main() {
  const explicitDatabases = process.argv
    .slice(2)
    .filter((arg) => !arg.startsWith('--'));
  const databases = explicitDatabases.length ? explicitDatabases : defaultDatabases;
  const report = {
    generated_at: new Date().toISOString(),
    databases: [],
  };

  for (const database of databases) {
    report.databases.push(await auditDatabase(database));
  }

  if (jsonOutput) console.log(JSON.stringify(report, null, 2));
  else console.log(renderHuman(report));
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
