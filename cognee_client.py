"""Thin async helpers around cognee 1.x (verified against cognee 1.6.10).

Signatures used:
  serve(url=None, api_key=None)            -> falls back to COGNEE_SERVICE_URL / COGNEE_API_KEY
  remember(data, dataset_name="main_dataset", ...)
  recall(query_text, query_type=None, *, datasets=[...], include_references=..., ...)
  disconnect(clear_saved=False)
All four are coroutines.
"""
import os

from dotenv import load_dotenv

load_dotenv()

import cognee  # noqa: E402  (import after load_dotenv so cognee sees the env)
from cognee import SearchType  # noqa: E402


async def connect():
    """Connect to the Cognee service using COGNEE_SERVICE_URL / COGNEE_API_KEY."""
    return await cognee.serve(
        url=os.getenv("COGNEE_SERVICE_URL") or None,
        api_key=os.getenv("COGNEE_API_KEY") or None,
    )


async def remember(text: str, dataset_name: str):
    """Ingest text and build the graph in one step."""
    return await cognee.remember(text, dataset_name=dataset_name)


async def recall(query: str, datasets: list[str] | None = None, top_k: int = 15):
    """Graph-completion style query, restricted to the given datasets."""
    return await cognee.recall(
        query,
        query_type=SearchType.GRAPH_COMPLETION,
        datasets=datasets,
        top_k=top_k,
        include_references=True,
    )


async def disconnect():
    await cognee.disconnect()
