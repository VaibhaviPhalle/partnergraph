"""Explain each match using Cognee cloud (graph completion), with an LLM fallback.

remember() runs in the background on cloud, so we remember ALL companies first and
then poll recall (every 10s, up to 2 min total). This module never raises.
"""
import asyncio
import os
import re
import time

from extract import cached_urls, complete
from models import CompanyProfile, Match

OWN_KEY = os.getenv("MY_COMPANY_KEY", "partnergraph")
POLL_SECONDS = 10
DEADLINE_SECONDS = 120
URL_RE = re.compile(r"https?://[^\s)\]>\"']+")


def render_profile(p: CompanyProfile) -> str:
    """Plain sentences, each carrying its source URL where one exists."""
    out = [f"{p.name} is a company; its website is {p.url}."]
    if p.capabilities:
        out.append(f"{p.name} capabilities: {'; '.join(p.capabilities)}. (source: {p.url})")
    if p.problems_solved:
        out.append(f"{p.name} solves these problems: {'; '.join(x.label for x in p.problems_solved)}. (source: {p.url})")
    if p.segments:
        out.append(f"{p.name} serves these segments: {', '.join(p.segments)}.")
    if p.tech_stack:
        out.append(f"{p.name} tech stack: {', '.join(p.tech_stack)}.")
    if p.integrations:
        out.append(f"{p.name} integrates with: {', '.join(p.integrations)}.")
    for s in p.signals:
        out.append(f'{p.name} says "{s.quote}" (source: {s.source_url}). '
                   f"This is a {s.type} signal about {s.problem_id}.")
    return "\n".join(out)


def clean_answer(text: str, allowed: set[str]) -> str:
    """Drop Cognee's evidence footer and any URL not in the allowed cached set."""
    text = re.split(r"\n\s*Evidence:", text)[0].strip()

    def ok(u: str) -> bool:
        return u.rstrip(".,;:") in allowed

    # [label](url) with a bad url -> just the label
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
                  lambda m: m.group(0) if ok(m.group(2)) else m.group(1), text)
    text = URL_RE.sub(lambda m: m.group(0) if ok(m.group(0)) else "", text)
    return re.sub(r"[ \t]+", " ", re.sub(r"\(\s*\)", "", text)).strip()


NOT_FOUND_RE = re.compile(r"could not find|couldn't find|cannot find|can't find|no (relevant )?(information|answer|data)|don't have (enough )?(information|context)", re.I)


def _usable(text: str) -> bool:
    """A real, cited answer: not a 'not found' reply, and still contains >=1 allowed URL."""
    return bool(text) and not NOT_FOUND_RE.search(text) and bool(URL_RE.search(text))


def _result_text(results) -> str:
    for r in results or []:
        t = r.get("text") if isinstance(r, dict) else getattr(r, "text", None)
        if t:
            return t
    return ""


def fallback_explanation(match: Match, name: str, own_name: str) -> str:
    """One LLM call over the evidence list; deterministic string if that fails too."""
    ev = match.evidence[:12]
    if not ev:
        return f"No evidence found linking {name} to {own_name}."
    lines = "\n".join(f"- {e.claim} (source: {e.source_url})" for e in ev)
    prompt = (f"In 2-3 sentences explain why {name} is a {match.type} for {own_name}. Use ONLY these facts, "
              f"cite the source URLs given, add nothing else:\n{lines}")
    try:
        return complete([{"role": "user", "content": prompt}], json_mode=False).strip()
    except Exception as e:  # noqa: BLE001
        print(f"  fallback LLM failed ({type(e).__name__}); using evidence text")
        return f"Evidence for {name} as a {match.type}: " + " ".join(
            f"{e.claim} ({e.source_url})" for e in ev[:3])


async def explain_all(profiles: dict[str, CompanyProfile], matches: list[Match],
                      use_cognee: bool = True) -> None:
    """Fills match.explanation / explanation_source in place."""
    async def fallback(m):
        m.explanation = await asyncio.to_thread(fallback_explanation, m, profiles[m.target_key].name, profiles[OWN_KEY].name)
        m.explanation_source = "fallback"

    if not use_cognee:  # litellm fallback only; never touches cognee
        await asyncio.gather(*(fallback(m) for m in matches))
        return

    import cognee_client as cc

    connected = False
    try:
        await cc.connect()
        connected = True
        # 1) remember ALL companies first (background processing on cloud)
        remembered = set()
        for key, prof in profiles.items():
            try:
                await cc.remember(render_profile(prof), f"pg_{key}")
                remembered.add(key)
            except Exception as e:  # noqa: BLE001
                print(f"  remember failed for {key}: {type(e).__name__}: {str(e)[:150]}")
        deadline = time.monotonic() + DEADLINE_SECONDS
        own_ok = OWN_KEY in remembered

        # 2) poll recall per target until its graph is searchable
        async def one(m: Match):
            key = m.target_key
            if not own_ok or key not in remembered:
                return await fallback(m)
            name = profiles[key].name
            kind = "customer and partner" if m.type == "both" else m.type
            q = f"Why is {name} a {kind} for {profiles[OWN_KEY].name}? Use only facts with source URLs."
            allowed = cached_urls(key) | cached_urls(OWN_KEY)
            while True:
                try:
                    results = await cc.recall(q, [f"pg_{OWN_KEY}", f"pg_{key}"])
                    # recall answers per dataset; take the first answer that is cited and real
                    cleaned = [clean_answer(_result_text([r]), allowed) for r in results]
                    good = next((t for t in cleaned if _usable(t)), None)
                    if good:
                        m.explanation, m.explanation_source = good, "cognee"
                        return
                    # Evidence chunks present => graph is built and Cognee simply has no answer; don't wait.
                    if any("chunk" in str(r.get("text", "")) for r in results if isinstance(r, dict)):
                        print(f"  cognee retrieved chunks but gave no answer for {key}; using fallback")
                        break
                    # "no answer yet" / uncited answer: graph is probably still building
                    if time.monotonic() < deadline:
                        await asyncio.sleep(POLL_SECONDS)
                        continue
                    print(f"  no usable cognee answer for {key} within {DEADLINE_SECONDS}s")
                    break
                except Exception as e:  # noqa: BLE001
                    if "NoDataError" in str(e) and time.monotonic() < deadline:
                        await asyncio.sleep(POLL_SECONDS)
                        continue
                    print(f"  recall failed for {key}: {type(e).__name__}: {str(e)[:120]}")
                    break
            await fallback(m)

        await asyncio.gather(*(one(m) for m in matches))
    except Exception as e:  # noqa: BLE001  never crash the pipeline
        print(f"  cognee explain error: {type(e).__name__}: {str(e)[:150]}")
        for m in matches:
            if not m.explanation:
                await fallback(m)
    finally:
        if connected:
            try:
                await cc.disconnect()
            except Exception:  # noqa: BLE001
                pass
