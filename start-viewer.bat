@echo off
echo Starting CNC Tool Database Viewer...
start http://127.0.0.1:8080
node "%~dp0server.js"
