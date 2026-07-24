const path = require('path');
const {
  close,
  defaultDbPath,
  loadProposal,
  openDb,
  validateProposal,
} = require('./cutting-data-common');

function usage() {
  return [
    'Usage: node scripts/validate-cutting-data-proposal.js <proposal.json> [--db path/to/db_v2.sqlite] [--json]',
    '',
    'Validates cutting-data proposals without writing to the database.',
  ].join('\n');
}

function argValue(flag) {
  const index = process.argv.indexOf(flag);
  return index >= 0 ? process.argv[index + 1] : null;
}

function proposalArg() {
  const args = process.argv.slice(2);
  return args.filter((arg, index) => !arg.startsWith('--') && args[index - 1] !== '--db')[0] || null;
}

async function main() {
  const jsonOutput = process.argv.includes('--json');
  const proposalPath = proposalArg();

  if (!proposalPath) {
    console.log(usage());
    return;
  }

  const dbPath = path.resolve(argValue('--db') || defaultDbPath);
  const { absolutePath, proposal } = loadProposal(proposalPath);
  const db = openDb(dbPath);
  try {
    const result = await validateProposal(proposal, db);
    const report = {
      proposal: absolutePath,
      database: dbPath,
      ok: result.ok,
      rows: Array.isArray(proposal.rows) ? proposal.rows.length : 0,
      accepted_rows: result.acceptedRows.length,
      errors: result.errors,
      warnings: result.warnings,
    };

    if (jsonOutput) {
      console.log(JSON.stringify(report, null, 2));
    } else {
      console.log(`Proposal: ${report.proposal}`);
      console.log(`Database: ${report.database}`);
      console.log(`Rows: ${report.rows}`);
      console.log(`Accepted rows: ${report.accepted_rows}`);
      console.log(`Errors: ${report.errors.length}`);
      console.log(`Warnings: ${report.warnings.length}`);
      for (const error of report.errors) {
        console.log(`ERROR row=${error.row || '-'} code=${error.code}: ${error.message}`);
      }
      for (const warning of report.warnings) {
        console.log(`WARN row=${warning.row || '-'} code=${warning.code}: ${warning.message}`);
      }
    }

    if (!result.ok) process.exitCode = 1;
  } finally {
    await close(db);
  }
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
