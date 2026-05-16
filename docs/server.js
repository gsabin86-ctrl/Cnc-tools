const http = require('http');
const fs = require('fs');
const path = require('path');

// Serve viewer files from this directory, db.sqlite from parent
const VIEWER_DIR = __dirname;
const DB_PATH = path.join(__dirname, 'db.sqlite');

http.createServer((req, res) => {
  let filePath;
  if (req.url === '/' || req.url === '/index.html') {
    filePath = path.join(VIEWER_DIR, 'index.html');
  } else if (req.url === '/db.sqlite') {
    filePath = DB_PATH;
  } else {
    filePath = path.join(VIEWER_DIR, req.url);
  }

  const extname = String(path.extname(filePath)).toLowerCase();
  const contentType = {
    '.html': 'text/html',
    '.json': 'application/json',
    '.sqlite': 'application/octet-stream'
  }[extname] || 'application/octet-stream';

  fs.readFile(filePath, (err, content) => {
    if (err) {
      res.writeHead(404);
      res.end('Not found: ' + req.url);
      return;
    }
    res.writeHead(200, { 'Content-Type': contentType });
    res.end(content, 'utf-8');
  });
}).listen(8080);

console.log('Server running at http://127.0.0.1:8080/');
