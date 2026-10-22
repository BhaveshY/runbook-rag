import argparse
import asyncio
import json

from .config import Settings


def main():
    parser = argparse.ArgumentParser(description="Runbook: build the corpus, serve the app, or measure quality.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ingest", help="Fetch pinned docs and build an immutable hybrid index")
    serve = sub.add_parser("serve", help="Serve the UI and API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    evaluate = sub.add_parser("evaluate", help="Run retrieval ablations and optional answer evaluation")
    evaluate.add_argument("--answers", action="store_true", help="Generate answers and run an independent, source-conditioned LLM judge (paid)")
    evaluate.add_argument("--split", choices=["dev", "holdout", "all"], default="all")
    evaluate.add_argument("--output", default="eval/results/latest.json")
    args = parser.parse_args()
    if args.command == "ingest":
        from .ingest import ingest
        result = asyncio.run(ingest(Settings()))
        print(json.dumps({key: result[key] for key in ("corpus_id", "documents", "chunks", "embedding_tokens")}, indent=2))
    elif args.command == "serve":
        import uvicorn
        uvicorn.run("runbook.api:app", host=args.host, port=args.port, proxy_headers=False, access_log=False)
    else:
        from .evaluate import evaluate
        asyncio.run(evaluate(Settings(), args.answers, args.split, args.output))

