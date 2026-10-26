import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

DOCS = {
    "images": "content/en/docs/concepts/containers/images.md",
    "pod-lifecycle": "content/en/docs/concepts/workloads/pods/pod-lifecycle.md",
    "resources": "content/en/docs/concepts/configuration/manage-resources-containers.md",
}
REVISION = "0123456789abcdef0123456789abcdef01234567"


def diagnosis(request: dict) -> dict:
    source = request["sources"][0]
    cite = [
        {
            "source_id": source["source_id"],
            "quote": " ".join(source["text"].split())[:90],
        }
    ]
    return {
        "status": "supported",
        "title": "Image pull",
        "claims": [{"text": "The passage explains the status.", "citations": cite}],
        "checks": [
            {
                "purpose": "Inspect events",
                "command": "kubectl describe pod POD_NAME",
                "expected_signal": "Pull errors",
                "citations": cite,
            }
        ],
        "follow_up": [],
        "limitation": "No cluster access.",
    }


ANSWERS = {
    "passage_ranking": lambda r: {"ranking": list(range(min(16, len(r["passages"]))))},
    "diagnosis": diagnosis,
    "citation_support": lambda r: {
        "claims": [True] * len(r["claims"]),
        "checks": [True] * len(r["checks"]),
    },
}


class FakeOpenAI(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        name = body["text"]["format"]["name"]
        output = ANSWERS[name](json.loads(body["input"][1]["content"]))
        text = [{"type": "output_text", "text": json.dumps(output)}]
        reply = {
            "status": "completed",
            "model": body["model"],
            "output": [{"content": text}],
        }
        payload = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


FAKE_CODEX = f"""
import json, sys
from pathlib import Path
sys.path.insert(0, {str(Path(__file__).parent)!r})
from test_e2e import ANSWERS
name = Path(sys.argv[sys.argv.index("--output-schema") + 1]).stem
answer = ANSWERS[name](json.loads(sys.stdin.read().rsplit("\\n", 1)[-1]))
reply = {{"type": "agent_message", "text": json.dumps(answer)}}
print(json.dumps({{"type": "item.completed", "item": reply}}))
print(json.dumps({{"type": "turn.completed", "usage": {{"input_tokens": 1}}}}))
"""


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module", params=["codex", "openai"])
def app(request, tmp_path_factory):
    data = tmp_path_factory.mktemp("data")
    raw = data / "raw" / REVISION
    raw.mkdir(parents=True)
    for name in DOCS:
        shutil.copy(f"tests/fixtures/docs/{name}.md", raw / f"{name}.md")
    (data / "sources.json").write_text(
        json.dumps(
            {
                "version": "1.35",
                "repository": "kubernetes/website",
                "revision": REVISION,
                "license": "CC-BY-4.0",
                "documents": [{"id": k, "path": v} for k, v in DOCS.items()],
            }
        )
    )
    codex = tmp_path_factory.mktemp("bin") / "codex"
    (codex.parent / "fake_codex.py").write_text(FAKE_CODEX)
    codex.write_text(
        f'#!/bin/sh\nexec "{sys.executable}" "{codex.parent}/fake_codex.py" "$@"\n'
    )
    codex.chmod(0o755)
    openai = ThreadingHTTPServer(("127.0.0.1", 0), FakeOpenAI)
    threading.Thread(target=openai.serve_forever, daemon=True).start()
    env = os.environ | {
        "PATH": f"{codex.parent}{os.pathsep}/usr/bin{os.pathsep}/bin",
        "RUNBOOK_BACKEND": request.param,
        "RUNBOOK_DATA_DIR": str(data),
        "RUNBOOK_MODEL_CACHE": str(Path(".pytest_cache/models").resolve()),
        "RUNBOOK_EVAL_REPORT": str(data / "report.json"),
        "OPENAI_API_KEY": "sk-test",
        "OPENAI_BASE_URL": f"http://127.0.0.1:{openai.server_port}/v1",
        "RUNBOOK_ACCESS_TOKEN": "token",
    }
    run = [sys.executable, "-m", "runbook"]
    subprocess.run([*run, "ingest"], env=env, check=True, capture_output=True)
    again = subprocess.run([*run, "ingest"], env=env, check=True, capture_output=True)
    assert b"Reusing" in again.stdout
    port = free_port()
    server = subprocess.Popen([*run, "serve", "--port", str(port)], env=env)
    client = httpx.Client(
        base_url=f"http://127.0.0.1:{port}",
        headers={"Authorization": "Bearer token"},
        timeout=60,
    )
    for _ in range(100):
        try:
            if client.get("/api/health").status_code == 200:
                break
        except httpx.TransportError:
            time.sleep(0.1)
    yield client
    server.terminate()
    server.wait()
    openai.shutdown()


def test_ingested_corpus_is_served(app):
    assert app.get("/api/health").json()["status"] == "ready"
    assert app.get("/api/corpus").json()["documents"] == 3
    assert "<title>" in app.get("/").text


@pytest.mark.parametrize("mode", ["bm25", "dense", "hybrid", "reranked"])
def test_every_retrieval_mode(app, mode):
    query = {"query": "pod stuck in ImagePullBackOff", "mode": mode, "k": 3}
    sources = app.post("/api/search", json=query).json()["sources"]
    assert len(sources) == 3
    if mode == "bm25":
        assert sources[0]["heading"] == "ImagePullBackOff"


def test_streamed_diagnosis_cites_retrieved_text(app):
    query = {"query": "My pod is stuck in ImagePullBackOff"}
    blocks = app.post("/api/diagnose/stream", json=query).text.strip().split("\n\n")
    events = [(b.split("\n")[0][7:], json.loads(b.split("\n")[1][6:])) for b in blocks]
    assert [name for name, _ in events] == ["status", "evidence", "status", "answer"]
    result = events[-1][1]
    assert result["answer"]["status"] == "supported"
    quote = result["answer"]["claims"][0]["citations"][0]["quote"]
    assert any(quote in " ".join(s["text"].split()) for s in result["sources"])


def test_requests_are_guarded(app):
    query = {"query": "My pod is stuck in ImagePullBackOff", "mode": "bm25"}
    assert (
        app.post("/api/search", json=query, headers={"Authorization": ""}).status_code
        == 401
    )
    assert app.post("/api/search", json={"query": "short"}).status_code == 422
    assert app.post("/api/search", content=b" " * 20_000).status_code == 413
