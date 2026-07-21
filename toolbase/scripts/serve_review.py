#!/usr/bin/env python3
"""Serve a private, loopback-only review screen and render cited PDF pages."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import shutil
import subprocess
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEW_ROOT = REPO_ROOT / "toolbase" / "review"
CACHE_ROOT = REPO_ROOT / "toolbase" / "build" / "review_pages"
DEFAULT_PROPOSAL = REPO_ROOT / "toolbase" / "proposals" / "kennametal-topswiss-identity-batch-01.json"
DEFAULT_LEDGER = REPO_ROOT / "toolbase" / "reviews" / "kennametal-topswiss-identity-batch-01.decisions.json"


def render_page(source: dict, page: int) -> Path:
    if not 1 <= page <= int(source.get("page_count") or 0):
        raise ValueError("page is outside the cited source")
    pdf_path = REPO_ROOT / source["local_path"]
    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)
    target_dir = CACHE_ROOT / source["content_sha256"]
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"page-{page}.png"
    if target.is_file():
        return target
    executable = shutil.which("pdftoppm")
    if not executable:
        raise RuntimeError("pdftoppm is required to render catalog pages")
    executable_path = Path(executable)
    if executable_path.suffix.lower() in {".cmd", ".bat"}:
        bundled_executable = (
            executable_path.parents[2] / "native" / "poppler" / "Library" / "bin" / "pdftoppm.exe"
        )
        if bundled_executable.is_file():
            executable = str(bundled_executable)
    prefix = target.with_suffix("")
    command = [
        executable,
        "-f",
        str(page),
        "-l",
        str(page),
        "-singlefile",
        "-png",
        "-r",
        "150",
        str(pdf_path),
        str(prefix),
    ]
    if executable.lower().endswith((".cmd", ".bat")):
        command = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", *command]
    subprocess.run(command, check=True, capture_output=True)
    if not target.is_file():
        raise RuntimeError("catalog page render did not produce an image")
    return target


def handler_factory(proposal_path: Path, ledger_path: Path):
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    source_by_id = {source["source_id"]: source for source in proposal["sources"]}

    class ReviewHandler(BaseHTTPRequestHandler):
        def send_bytes(self, body: bytes, content_type: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def send_json(self, payload: dict, status: int = 200) -> None:
            self.send_bytes(
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                "application/json; charset=utf-8",
                status,
            )

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            parsed = urllib.parse.urlparse(self.path)
            try:
                if parsed.path == "/api/proposal":
                    self.send_bytes(proposal_path.read_bytes(), "application/json; charset=utf-8")
                    return
                if parsed.path == "/api/ledger":
                    self.send_bytes(ledger_path.read_bytes(), "application/json; charset=utf-8")
                    return
                if parsed.path == "/api/source-page":
                    query = urllib.parse.parse_qs(parsed.query)
                    source_id = (query.get("source_id") or [""])[0]
                    page = int((query.get("page") or ["0"])[0])
                    if source_id not in source_by_id:
                        self.send_json({"error": "unknown source"}, 404)
                        return
                    image_path = render_page(source_by_id[source_id], page)
                    self.send_bytes(image_path.read_bytes(), "image/png")
                    return
                requested = "index.html" if parsed.path in {"", "/"} else parsed.path.lstrip("/")
                static_path = (REVIEW_ROOT / requested).resolve()
                if REVIEW_ROOT.resolve() not in static_path.parents and static_path != REVIEW_ROOT.resolve():
                    self.send_json({"error": "invalid path"}, 400)
                    return
                if not static_path.is_file():
                    self.send_json({"error": "not found"}, 404)
                    return
                content_type = mimetypes.guess_type(static_path.name)[0] or "application/octet-stream"
                self.send_bytes(static_path.read_bytes(), content_type)
            except Exception as exc:  # local reviewer needs the exact failure
                self.send_json({"error": str(exc)}, 500)

        def log_message(self, format: str, *args) -> None:
            print(f"review: {format % args}")

    return ReviewHandler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", type=Path, default=DEFAULT_PROPOSAL)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(
        ("127.0.0.1", args.port),
        handler_factory(args.proposal.resolve(), args.ledger.resolve()),
    )
    print(f"Private review screen: http://127.0.0.1:{args.port}")
    print("Decisions stay in browser storage until you export the ledger JSON.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
