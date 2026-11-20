"""extract -> score -> explain -> data/matches.json (the UI reads only that file)."""
import argparse
import asyncio
import json
from pathlib import Path

import pandas as pd

import extract
import score
from explain import explain_all

ROOT = Path(__file__).parent


def print_table(matches) -> None:
    if not matches:
        print("\nNo matches produced (no target profiles available).")
        return
    df = pd.DataFrame([{
        "rank": i, "target": m.target_key, "type": m.type,
        "customer": m.customer_score, "partner": m.partner_score,
        "evidence": len(m.evidence), "expl_src": m.explanation_source,
        "explanation": m.explanation.replace("\n", " ")[:80],
    } for i, m in enumerate(matches, 1)])
    print("\n" + df.to_string(index=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-run LLM extraction")
    ap.add_argument("--no-cognee", action="store_true", help="explain with the litellm fallback only")
    args = ap.parse_args()

    matches = []
    try:
        profiles = extract.run(refresh=args.refresh)
        matches = score.score_all(profiles)
        asyncio.run(explain_all(profiles, matches, use_cognee=not args.no_cognee))
        matches.sort(key=lambda m: max(m.customer_score, m.partner_score), reverse=True)
        out = ROOT / "data" / "matches.json"
        out.write_text(json.dumps([m.model_dump() for m in matches], indent=2))
        print(f"\nSaved {out}")
    finally:
        print_table(matches)  # always print, even if a step failed


if __name__ == "__main__":
    main()
