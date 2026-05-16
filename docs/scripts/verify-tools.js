const fs = require('fs');
const path = require('path');
const sqlite3 = require('sqlite3').verbose();

const root = path.resolve(__dirname, '..');
const dbPath = path.join(root, 'db.sqlite');

const manufacturerSourceDomains = {
  'Iscar': ['iscar.com', 'webshop.iscar'],
  'Kennametal': ['kennametal.com'],
  'Mitsubishi Materials': ['mmc-carbide.com', 'mitsubishicarbide.com', 'mitsubishicarbide.net'],
  'PH Horn': ['horn-eshop', 'phorn', 'horn-group.com', 'hornusa.com'],
  'Horn': ['horn-eshop', 'phorn', 'horn-group.com', 'hornusa.com'],
  'Sandvik Coromant': ['sandvik.coromant.com', 'sandvik.com'],
  'Star Micronics': ['starcnc.com', 'star-m.jp', 'starmicronics.com'],
  'Tungaloy': ['tungaloy.com'],
};

const secondarySourceDomains = [
  'toolsunited.com',
  'rothhaas-online.de',
];

const weakSourcePatterns = [
  /\bdocumentation\b/i,
  /\bcatalog\b/i,
  /\.pdf\b/i,
  /\bmanual\b/i,
];

const riskyTextPatterns = [
  { pattern: /\blikely\b/i, label: 'contains likely/estimated wording' },
  { pattern: /\bdepends\b/i, label: 'contains dependency wording' },
  { pattern: /\bwith modification\b/i, label: 'contains modified-fit wording' },
  { pattern: /\bunresolved\b/i, label: 'contains unresolved compatibility note' },
  { pattern: /\be\.g\./i, label: 'contains example-based compatibility wording' },
  { pattern: /\bvarious materials\b/i, label: 'contains broad material claim' },
  { pattern: /\bcompletes\b/i, label: 'contains inferred/completion wording' },
];

function openDb() {
  return new sqlite3.Database(dbPath);
}

function all(db, sql, params = []) {
  return new Promise((resolve, reject) => {
    db.all(sql, params, (err, rows) => (err ? reject(err) : resolve(rows)));
  });
}

function parseJson(value, fallback = null) {
  if (value == null || String(value).trim() === '') return fallback;
  try {
    return JSON.parse(value);
  } catch {
    return fallback;
  }
}

function sourcesFor(row) {
  const sources = parseJson(row.sources, []);
  return Array.isArray(sources) ? sources.map((source) => String(source).trim()).filter(Boolean) : [];
}

function specsFor(row) {
  const specs = parseJson(row.specs, {});
  return specs && typeof specs === 'object' && !Array.isArray(specs) ? specs : {};
}

function normalize(value) {
  return String(value || '').replace(/[^A-Z0-9]/gi, '').toUpperCase();
}

function isUrl(value) {
  return /^https?:\/\//i.test(value);
}

function sourceDomain(source) {
  if (!isUrl(source)) return null;
  try {
    return new URL(source).hostname.replace(/^www\./, '').toLowerCase();
  } catch {
    return null;
  }
}

function sourceTier(row, source) {
  const domain = sourceDomain(source);
  if (!domain) return 'local_or_text';

  const accepted = manufacturerSourceDomains[row.manufacturer] || [];
  if (accepted.some((item) => domain.includes(item))) return 'manufacturer';
  if (secondarySourceDomains.some((item) => domain.includes(item))) return 'secondary';
  return 'external';
}

function addFinding(findings, row, severity, code, message, evidence = {}) {
  findings.push({
    severity,
    code,
    json_id: row.json_id,
    component_type: row.component_type,
    manufacturer: row.manufacturer,
    message,
    evidence,
  });
}

function validateIso(row, specs, findings) {
  if (row.component_type !== 'insert') return;
  const specIso = specs.iso_id || specs.iso_catalog_id || specs.ISO || specs.iso;
  if (!specIso) return;

  const specBase = normalize(specIso);
  const rowBase = normalize(row.iso_designation || row.json_id);
  if (specBase && rowBase && !specBase.startsWith(rowBase) && !rowBase.startsWith(specBase.slice(0, Math.min(specBase.length, rowBase.length)))) {
    addFinding(findings, row, 'high', 'iso_mismatch', 'ISO designation does not line up with specs.iso_id.', {
      row_iso_designation: row.iso_designation,
      specs_iso_id: specIso,
    });
  }
}

function validateSourceCoverage(row, findings) {
  const sources = sourcesFor(row);
  if (!sources.length) {
    addFinding(findings, row, 'high', 'missing_source', 'Row has no source attached.');
    return;
  }

  const tiers = sources.map((source) => sourceTier(row, source));
  const hasManufacturerSource = tiers.includes('manufacturer');
  const hasOnlyTextSources = tiers.every((tier) => tier === 'local_or_text');
  const weakSources = sources.filter((source) => !isUrl(source) || weakSourcePatterns.some((pattern) => pattern.test(source)));

  if (!hasManufacturerSource && !['Generic', null].includes(row.manufacturer)) {
    addFinding(findings, row, 'medium', 'no_manufacturer_source', 'No manufacturer-domain source is attached.', {
      sources,
      source_tiers: tiers,
    });
  }

  if (hasOnlyTextSources) {
    addFinding(findings, row, 'medium', 'text_only_sources', 'Sources are text/local references only; external verification is needed.', { sources });
  } else if (weakSources.length) {
    addFinding(findings, row, 'low', 'weak_source_label', 'At least one source is a generic catalog/manual/documentation label.', { weak_sources: weakSources });
  }
}

function validateRiskyClaims(row, specs, findings) {
  const text = [
    row.description,
    row.geometry,
    row.insert_seat,
    JSON.stringify(specs),
  ].filter(Boolean).join('\n');

  for (const { pattern, label } of riskyTextPatterns) {
    if (pattern.test(text)) {
      addFinding(findings, row, 'medium', 'needs_claim_review', label, {
        match: String(pattern),
      });
    }
  }
}

function validateCompatibility(row, specs, findings) {
  const notes = Array.isArray(specs.compatibility_notes) ? specs.compatibility_notes : [];
  if (notes.some((note) => /^Unresolved/i.test(note))) {
    addFinding(findings, row, 'medium', 'unresolved_compatibility_note', 'Compatibility notes still contain unresolved entries.', {
      compatibility_notes: notes.filter((note) => /^Unresolved/i.test(note)),
    });
  }
}

function validateManufacturer(row, findings) {
  if (row.manufacturer === 'Horn') {
    addFinding(findings, row, 'low', 'manufacturer_alias', 'Manufacturer uses Horn while most rows use PH Horn; verify preferred canonical name.', {});
  }
  if (!row.manufacturer && row.component_type !== 'spare') {
    addFinding(findings, row, 'high', 'missing_manufacturer', 'Non-spare row has no manufacturer.', {});
  }
}

function rankSeverity(severity) {
  return { high: 3, medium: 2, low: 1 }[severity] || 0;
}

function summarize(findings, rows) {
  const bySeverity = findings.reduce((acc, finding) => {
    acc[finding.severity] = (acc[finding.severity] || 0) + 1;
    return acc;
  }, {});

  const byCode = findings.reduce((acc, finding) => {
    acc[finding.code] = (acc[finding.code] || 0) + 1;
    return acc;
  }, {});

  const rowsWithFindings = new Set(findings.map((finding) => finding.json_id));

  const rowScores = [...rowsWithFindings].map((jsonId) => {
    const rowFindings = findings.filter((finding) => finding.json_id === jsonId);
    return {
      json_id: jsonId,
      score: rowFindings.reduce((sum, finding) => sum + rankSeverity(finding.severity), 0),
      findings: rowFindings.length,
      codes: [...new Set(rowFindings.map((finding) => finding.code))],
    };
  }).sort((a, b) => b.score - a.score || b.findings - a.findings || a.json_id.localeCompare(b.json_id));

  return {
    rows: rows.length,
    rows_with_findings: rowsWithFindings.size,
    findings: findings.length,
    by_severity: bySeverity,
    by_code: byCode,
    highest_risk_rows: rowScores.slice(0, 30),
  };
}

async function main() {
  if (!fs.existsSync(dbPath)) throw new Error(`Missing database: ${dbPath}`);

  const db = openDb();
  const rows = await all(db, 'SELECT * FROM tools ORDER BY id');
  const findings = [];

  for (const row of rows) {
    const specs = specsFor(row);
    validateManufacturer(row, findings);
    validateSourceCoverage(row, findings);
    validateIso(row, specs, findings);
    validateRiskyClaims(row, specs, findings);
    validateCompatibility(row, specs, findings);
  }

  db.close();

  const report = {
    generated_at: new Date().toISOString(),
    summary: summarize(findings, rows),
    findings: findings
      .sort((a, b) => rankSeverity(b.severity) - rankSeverity(a.severity) || a.json_id.localeCompare(b.json_id))
      .slice(0, 200),
  };

  console.log(JSON.stringify(report, null, 2));
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
