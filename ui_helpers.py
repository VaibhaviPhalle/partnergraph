"""Read-only data loading helpers for the Streamlit UI. No LLM / cognee calls."""
import json
from pathlib import Path

import pandas as pd

DATA = Path(__file__).parent / "data"


def _load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return default


def load_seeds() -> dict:
    return _load(DATA / "seeds.json", {})


def load_matches() -> list[dict]:
    return _load(DATA / "matches.json", [])


def load_profiles() -> dict[str, dict]:
    profiles = {}
    for p in sorted((DATA / "profiles").glob("*.json")):
        d = _load(p, None)
        if d:
            profiles[d.get("key", p.stem)] = d
    return profiles


def company_name(key: str, seeds: dict, profiles: dict) -> str:
    return (profiles.get(key, {}).get("name")
            or seeds.get(key, {}).get("name") or key)


def ranked_frame(matches: list[dict], seeds: dict, profiles: dict,
                 sort_col: str | None = None) -> pd.DataFrame:
    rows = [{
        "company": company_name(m["target_key"], seeds, profiles),
        "type": m.get("type", ""),
        "customer_score": m.get("customer_score", 0),
        "partner_score": m.get("partner_score", 0),
        "evidence": len(m.get("evidence", [])),
    } for m in matches]
    df = pd.DataFrame(rows, columns=["company", "type", "customer_score",
                                     "partner_score", "evidence"])
    if df.empty:
        return df
    key = df[sort_col] if sort_col else df[["customer_score", "partner_score"]].max(axis=1)
    return df.assign(_k=key).sort_values("_k", ascending=False, kind="stable").drop(columns="_k").reset_index(drop=True)


def explanation_text(m: dict) -> str | None:
    """Return the explanation, or None if it is empty / a 'not found' placeholder."""
    text = (m.get("explanation") or "").strip()
    if not text or "could not find" in text.lower():
        return None
    return text


# ---------------------------------------------------------------- founder profile
ME_PATH = DATA / "me.json"
GOALS = {"Find customers": "customer_score", "Find partners": "partner_score"}
TONES = ["Casual", "Formal"]
DEFAULT_ME = {"name": "", "company_url": "partnergraph", "goal": "Find customers", "tone": "Casual"}


def load_me() -> dict:
    me = {**DEFAULT_ME, **_load(ME_PATH, {})}
    if me["goal"] not in GOALS:
        me["goal"] = DEFAULT_ME["goal"]
    if me["tone"] not in TONES:
        me["tone"] = DEFAULT_ME["tone"]
    return me


def save_me(me: dict) -> None:
    ME_PATH.write_text(json.dumps(me, indent=2))


def company_from_url(url: str) -> str:
    """'https://www.cognee.ai/x' -> 'Cognee'."""
    host = url.strip().lower().split("//")[-1].split("/")[0].removeprefix("www.")
    return host.split(".")[0].capitalize() if host else "my company"


# ---------------------------------------------------------------- email drafts
def _own_profile(me: dict, profiles: dict) -> dict | None:
    stem = company_from_url(me["company_url"]).lower()
    return profiles.get(stem)


def build_draft(me: dict, m: dict, profiles: dict, seeds: dict) -> str:
    """First-person draft from the founder, in their tone, tied to their goal.
    Deterministic template: the UI never calls an LLM. Only facts from the profiles are used."""
    target = company_name(m["target_key"], seeds, profiles)
    name = me["name"].strip() or "Your name"
    company = company_from_url(me["company_url"])
    casual = me["tone"] == "Casual"
    own = _own_profile(me, profiles)
    tgt = profiles.get(m["target_key"], {})
    vocab = {p["id"]: p["label"] for p in (own or {}).get("problems_solved", [])}

    # a real signal from the target that maps to one of my problems
    sig = next((s for s in sorted(tgt.get("signals", []), key=lambda s: -{"job": 3, "blog": 2}.get(s["type"], 1))
                if s["problem_id"] in vocab), None)

    customer = me["goal"] == "Find customers"
    goal_line = (f"I'm focused on finding customers right now, and {target} looks like a strong fit."
                 if customer else
                 f"I'm focused on finding partners right now, and {target} looks like a strong fit.")
    if not casual:
        goal_line = goal_line.replace("I'm", "I am")

    seen = f'I came across {sig["source_url"]}, which says: "{sig["quote"]}"' if sig else ""

    if customer:
        problem = vocab[sig["problem_id"]] if sig else (next(iter(vocab.values()), "") if vocab else "")
        ask = (f"That is the problem {company} solves ({problem.lower()}). "
               if problem else f"{company} may be able to help. ")
        ask += ("Happy to show you how in 15 minutes if it's useful." if casual
                else "I would welcome the opportunity to demonstrate this in a brief call.")
    else:
        shared = [e["claim"].split(": ", 1)[1] for e in m.get("evidence", [])
                  if e["claim"].startswith("Shared tech/integration:")]
        if shared:
            ask = f"We both work with {shared[0]}, so I'd like to propose an integration between {company} and {target}. "
        else:
            ask = f"I'd like to propose a referral arrangement between {company} and {target}, where we send each other relevant customers. "
        ask += ("Would you be up for a quick chat?" if casual
                else "Would you be available for a brief call to discuss?")

    hello = f"Hi {target} team," if casual else f"Dear {target} team,"
    intro = f"I'm {name}, founder of {company}." if casual else f"I am {name}, founder of {company}."
    close = "Cheers," if casual else "Kind regards,"
    body = " ".join(x for x in (intro, goal_line, seen, ask) if x)
    return f"{hello}\n\n{body}\n\n{close}\n{name}, founder of {company}"


def build_subject(me: dict, target: str) -> str:
    company = company_from_url(me["company_url"])
    what = "customer" if me["goal"] == "Find customers" else "partnership"
    return f"{company} x {target}: {what} idea"
