"""OpenAI-compatible LLM stub for local load testing (blueprint §7).

The staging API replicas point OPENROUTER_BASE_URL at this server, so the
full async path (client -> timebox -> provider -> JSON parse -> DB) runs
against a deterministic, latency-configurable provider:

    python scripts/loadtest_stub.py --port 9010 --latency 0.0   # baseline
    python scripts/loadtest_stub.py --port 9010 --latency 2.0   # provider scenario
"""

import argparse
import asyncio
import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()
LATENCY = 0.0

CANNED_REPLY = json.dumps({"reply": "ok", "memories": {}, "delete_memories": []})


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    await request.json()  # consume the body
    if LATENCY:
        await asyncio.sleep(LATENCY)
    return JSONResponse(
        {
            "id": "stub",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": CANNED_REPLY},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
    )


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9010)
    parser.add_argument("--latency", type=float, default=0.0, help="seconds to sleep per call")
    args = parser.parse_args()
    LATENCY = args.latency
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
