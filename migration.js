const fs = require('fs');
const sqlite3 = require('sqlite3').verbose();

let rawData = fs.readFileSync('tools.json', 'utf8');
let data = JSON.parse(rawData).tools;

let holders = [];
let inserts = [];

data.forEach(tool => {
  if (typeof tool !== 'object' || tool === null) return;

  let type = (tool.type || '').toLowerCase();
  let category = (tool.category || '').toLowerCase();

  if (type.includes('holder') || type.includes('adapter') || category.includes('holder') || category.includes('adapter')) {
    holders.push(tool);
  } else {
    inserts.push(tool);
  }
});

// Collect unique keys
let holderKeys = new Set();
holders.forEach(h => Object.keys(h).forEach(k => holderKeys.add(k)));

let insertKeys = new Set();
inserts.forEach(i => Object.keys(i).forEach(k => insertKeys.add(k)));

// Adjust for 'id' column
function getColumns(keysSet) {
  return Array.from(keysSet).map(k => k === 'id' ? 'json_id TEXT' : `${k} TEXT`).join(', ');
}

function getColsArray(keysSet) {
  return Array.from(keysSet).map(k => k === 'id' ? 'json_id' : k);
}

const db = new sqlite3.Database('db.sqlite');

db.serialize(() => {
  // Create holders table
  let holderColumns = getColumns(holderKeys);
  db.run(`CREATE TABLE IF NOT EXISTS holders (id INTEGER PRIMARY KEY AUTOINCREMENT, ${holderColumns})`);

  // Create inserts table
  let insertColumns = getColumns(insertKeys);
  db.run(`CREATE TABLE IF NOT EXISTS inserts (id INTEGER PRIMARY KEY AUTOINCREMENT, ${insertColumns})`);

  // Insert holders
  let allHolderCols = getColsArray(holderKeys);
  holders.forEach(h => {
    let values = Array.from(holderKeys).map(k => {
      let v = h[k];
      if (v === undefined) return null;
      if (typeof v === 'object' && v !== null) return JSON.stringify(v);
      return v;
    });
    let placeholders = allHolderCols.map(() => '?').join(', ');
    db.run(`INSERT INTO holders (${allHolderCols.join(', ')}) VALUES (${placeholders})`, values);
  });

  // Insert inserts
  let allInsertCols = getColsArray(insertKeys);
  inserts.forEach(i => {
    let values = Array.from(insertKeys).map(k => {
      let v = i[k];
      if (v === undefined) return null;
      if (typeof v === 'object' && v !== null) return JSON.stringify(v);
      return v;
    });
    let placeholders = allInsertCols.map(() => '?').join(', ');
    db.run(`INSERT INTO inserts (${allInsertCols.join(', ')}) VALUES (${placeholders})`, values);
  });
});

db.close(err => {
  if (err) {
    console.error(err.message);
  } else {
    fs.unlinkSync('tools.json');
    console.log(`Migration complete: ${holders.length} holders, ${inserts.length} inserts`);
  }
});
