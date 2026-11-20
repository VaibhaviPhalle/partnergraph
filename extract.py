"""Extract a CompanyProfile per company from cached pages using an LLM (litellm).

Usage: python extract.py [--refresh]
The "me" company (MY_COMPANY_KEY, default partnergraph) is extracted FIRST; its problems_solved
list becomes the controlled vocabulary for every target.
"""
import argparse
import json
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import litellm  # noqa: E402
from pydantic import BaseModel, ValidationError  # noqa: E402

from models import CompanyProfile, ProblemRef, Signal  # noqa: E402

litellm.suppress_debug_info = True

ROOT = Path(__file__).parent
SEEDS = ROOT / "data" / "seeds.json"
RAW = ROOT / "data" / "raw"
PROFILES = ROOT / "data" / "profiles"

OWN_KEY = os.getenv("MY_COMPANY_KEY", "partnergraph")
SEGMENTS = [
    "ai_app_builders", "data_engineering", "product_analytics", "ml_platform",
    "enterprise_it", "developer_tools", "ecommerce", "fintech",
]
# Signal type is derived from the cached page's type, not trusted from the LLM.
SIGNAL_TYPE = {
    "job": "job", "blog_post": "blog", "blog_index": "blog", "product": "product",
    "home": "product", "integrations": "integration", "careers": "other",
}


# ---------------------------------------------------------------- LLM helper
FALLBACK_MODEL = "gemini/gemini-flash-latest"
BACKOFF = (5, 15, 30)  # seconds, for 503 / 429 / timeout


def _call(model: str, messages, json_mode: bool) -> str:
    """One model: drops params the model rejects; retries 503/429/timeout with backoff."""
    kwargs = dict(
        model=model,
        api_key=os.getenv("GEMINI_API_KEY"),
        messages=messages,
        temperature=0,
        reasoning_effort="disable",
        timeout=90,
    )
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    optional = ["reasoning_effort", "temperature"]
    transient = 0
    while True:
        try:
            resp = litellm.completion(**kwargs)
            return resp.choices[0].message.content or ""
        except Exception as e:  # noqa: BLE001
            msg = str(e).lower()
            bad = next((p for p in optional if p in kwargs and (p in msg or (p == "reasoning_effort" and "thinking" in msg))), None)
            if bad is not None:
                print(f"  (model rejected '{bad}'; retrying without it)")
                kwargs.pop(bad)
                continue
            if isinstance(e, (litellm.ServiceUnavailableError, litellm.Timeout, litellm.RateLimitError)) and transient < len(BACKOFF):
                wait = BACKOFF[transient]
                transient += 1
                print(f"  ({type(e).__name__}; retry {transient}/{len(BACKOFF)} in {wait}s)")
                time.sleep(wait)
                continue
            raise


def complete(messages, json_mode=True) -> str:
    """EXTRACT_MODEL first; if it still fails after retries, ONE attempt on the -lite model."""
    primary = os.getenv("EXTRACT_MODEL", "gemini/gemini-2.5-flash")
    try:
        return _call(primary, messages, json_mode)
    except Exception as e:  # noqa: BLE001
        print(f"  {primary} failed ({type(e).__name__}: {str(e).splitlines()[0][:90]}); trying {FALLBACK_MODEL} once")
        return _call(FALLBACK_MODEL, messages, json_mode)


# ---------------------------------------------------------------- data access
def load_pages(key: str) -> list[dict]:
    files = sorted((RAW / key).glob("*.json"), key=lambda p: int(p.stem))
    return [json.loads(f.read_text()) for f in files]


PAGE_CAP = 2500       # chars per page sent to the LLM
TOTAL_CAP = 15000     # chars per company
PRIORITY = ["job", "blog_post", "integrations", "product", "home", "blog_index", "careers"]


def select_pages(pages: list[dict]) -> list[dict]:
    """Highest-value page types first, each capped, within a total character budget."""
    rank = {t: i for i, t in enumerate(PRIORITY)}
    chosen, used = [], 0
    for p in sorted(pages, key=lambda p: rank.get(p["page_type"], len(PRIORITY))):
        room = TOTAL_CAP - used
        if room < 200:
            break
        text = p["text"][: min(PAGE_CAP, room)]
        chosen.append({**p, "text": text})
        used += len(text)
    return chosen


def cached_urls(key: str) -> set[str]:
    return {p["url"] for p in load_pages(key)}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def _snake(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


# ---------------------------------------------------------------- prompting
class _Extraction(BaseModel):
    capabilities: list[str] = []
    problems_solved: list[ProblemRef] = []
    segments: list[str] = []
    tech_stack: list[str] = []
    integrations: list[str] = []
    signals: list[dict] = []


SHAPE = """Return ONE JSON object with exactly these keys:
{
  "capabilities": [short phrases],
  "problems_solved": [{"id": "snake_case_id", "label": "short human label"}],
  "segments": [subset of the allowed segment list],
  "tech_stack": [lowercase technologies/frameworks/languages/databases mentioned],
  "integrations": [lowercase names of products/platforms it integrates with],
  "signals": [{"problem_id": "...", "type": "job|blog|product|integration|other",
               "quote": "<=200 chars, copied VERBATIM from the page text", "source_url": "<the [SOURCE: url] the quote came from>"}]
}
Use only information present in the pages. Never invent quotes or URLs."""


def build_messages(name: str, pages: list[dict], vocab: list[ProblemRef] | None, retry_error: str | None):
    allowed_seg = ", ".join(SEGMENTS)
    if vocab is None:
        task = (
            f"You are profiling {name}, the company whose products we sell. From its pages extract its profile.\n"
            "problems_solved: 6-10 items, short snake_case ids (e.g. finding_customers, finding_partners, lead_research_time), the core customer "
            "problems this company solves. These ids become a controlled vocabulary.\n"
            "signals: up to 8 verbatim quotes showing which of those problems it addresses; problem_id must be one "
            "of your problems_solved ids."
        )
    else:
        v = "\n".join(f"- {p.id}: {p.label}" for p in vocab)
        task = (
            f"You are profiling {name}, a prospective customer/partner of a company that solves these problems:\n{v}\n"
            f"problems_solved: the problems {name}'s own products solve (snake_case ids; reuse a vocabulary id when it fits).\n"
            f"signals: up to 10 verbatim quotes showing {name} HAS or is working on one of the vocabulary problems "
            "(job descriptions, blog posts, product claims, integrations). Hiring for partnerships / business development / "
            "sales roles, and partner, marketplace or integrations pages, are strong signals of a need. problem_id MUST be one "
            'of the vocabulary ids above, or "other" if the quote fits none. Prefer job descriptions and blog posts that show real need.'
        )
    system = f"{task}\nsegments: choose ONLY from [{allowed_seg}].\n{SHAPE}"
    body = "\n\n".join(f"[SOURCE: {p['url']}]\n{p['title']}\n{p['text']}" for p in pages)
    user = f"Company: {name}\n\nPAGES:\n{body}"
    if retry_error:
        user += f"\n\nYour previous answer was rejected: {retry_error}\nReturn valid JSON only."
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


# ---------------------------------------------------------------- extraction
def extract_company(key: str, seed: dict, vocab: list[ProblemRef] | None) -> CompanyProfile:
    pages = load_pages(key)
    if not pages:
        raise RuntimeError(f"no cached pages for {key}; run crawl.py")
    by_url = {p["url"]: p for p in pages}  # full cached text, used for verbatim/URL checks
    sent = select_pages(pages)
    err = None
    for attempt in range(2):  # 1 retry
        try:
            raw = json.loads(complete(build_messages(seed["name"], sent, vocab, err)))
            for s in raw.get("signals", []):
                s["quote"] = str(s.get("quote", ""))[:200]
            ext = _Extraction.model_validate(raw)
            return _finalize(key, seed, ext, by_url, vocab)
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            err = str(e)[:400]
            print(f"  {key}: attempt {attempt + 1} failed ({err[:120]})")
        except Exception as e:  # noqa: BLE001  API errors etc.
            err = f"{type(e).__name__}: {str(e)[:300]}"
            print(f"  {key}: attempt {attempt + 1} failed ({err[:120]})")
    raise RuntimeError(f"extraction failed for {key}: {err}")


def _finalize(key, seed, ext: _Extraction, by_url: dict, vocab) -> CompanyProfile:
    problems, seen = [], set()
    for p in ext.problems_solved:
        pid = _snake(p.id)
        if pid and pid not in seen:
            seen.add(pid)
            problems.append(ProblemRef(id=pid, label=p.label))
    if vocab is None:
        if len(problems) < 6:
            raise ValueError(f"need 6-10 problems_solved, got {len(problems)}")
        problems = problems[:10]
    valid_ids = {p.id for p in (vocab or problems)}

    signals, dropped = [], 0
    for s in ext.signals:
        url, quote = s.get("source_url", ""), s.get("quote", "").strip()
        page = by_url.get(url)
        if page is None or not quote or _norm(quote) not in _norm(page["text"] + " " + page["title"]):
            dropped += 1  # unknown URL or quote not verbatim on that page
            continue
        pid = _snake(str(s.get("problem_id", "other")))
        if pid not in valid_ids:
            pid = "other"
        signals.append(Signal(problem_id=pid, type=SIGNAL_TYPE.get(page["page_type"], "other"),
                              quote=quote, source_url=url))
    if dropped:
        print(f"  {key}: dropped {dropped} signal(s) (bad source_url or non-verbatim quote)")

    return CompanyProfile(
        key=key, name=seed["name"], url=seed["home"],
        capabilities=[c.strip() for c in ext.capabilities if c.strip()],
        problems_solved=problems,
        segments=[s for s in dict.fromkeys(x.lower().strip() for x in ext.segments) if s in SEGMENTS],
        tech_stack=list(dict.fromkeys(t.lower().strip() for t in ext.tech_stack if t.strip())),
        integrations=list(dict.fromkeys(t.lower().strip() for t in ext.integrations if t.strip())),
        signals=signals,
    )


def load_profile(key: str) -> CompanyProfile:
    return CompanyProfile.model_validate_json((PROFILES / f"{key}.json").read_text())


def run(refresh: bool = False) -> dict[str, CompanyProfile]:
    seeds = json.loads(SEEDS.read_text())
    PROFILES.mkdir(parents=True, exist_ok=True)
    profiles: dict[str, CompanyProfile] = {}
    order = [OWN_KEY] + [k for k in seeds if k != OWN_KEY]  # "me" first
    vocab = None
    for key in order:
        path = PROFILES / f"{key}.json"
        if path.exists() and not refresh:
            prof = load_profile(key)
            print(f"{key:<12} cached")
        else:
            t0 = time.monotonic()
            try:
                prof = extract_company(key, seeds[key], vocab if key != OWN_KEY else None)
            except Exception as e:  # noqa: BLE001
                print(f"{key:<12} failed  {time.monotonic() - t0:5.1f}s  ({str(e).splitlines()[0][:100]})")
                if key == OWN_KEY:
                    raise  # no vocabulary, nothing else can run
                continue
            path.write_text(prof.model_dump_json(indent=2))  # saved immediately
            print(f"{key:<12} ok      {time.monotonic() - t0:5.1f}s  ({len(prof.signals)} signals)")
        profiles[key] = prof
        if key == OWN_KEY:
            vocab = prof.problems_solved
    return profiles


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    run(ap.parse_args().refresh)
