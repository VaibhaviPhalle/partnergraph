"""Crawl seed pages + job postings into data/raw/{company_key}/{n}.json.

Usage:
    python crawl.py             # fetch only what is not cached (offline-safe once cached)
    python crawl.py --refresh   # re-fetch everything
"""
import argparse
import html
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent
SEEDS = ROOT / "data" / "seeds.json"
RAW = ROOT / "data" / "raw"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA}
TIMEOUT = 10
MAX_CHARS = 6000
JOBS_PER_COMPANY = 2

STRIP_TAGS = ["script", "style", "nav", "footer", "header", "noscript", "svg", "form", "iframe"]

# Job title scoring: engineering/data roles, weighted toward AI/data/search/platform work.
ROLE_RE = re.compile(r"engineer|developer|data|machine learning|\bml\b|\bai\b|scientist|architect", re.I)
BOOST_RE = re.compile(r"\bai\b|\bml\b|machine learning|data|search|vector|platform|infrastructure|backend|integration", re.I)
EXCLUDE_RE = re.compile(r"sales|account|marketing|recruit|customer success|support engineer|solutions engineer|sdr|bdr", re.I)


def page_type(url: str, home: str) -> str:
    u = url.rstrip("/")
    path = urlparse(u).path.lower()
    if u == home.rstrip("/"):
        return "home"
    if re.search(r"career|/jobs", path):
        return "careers"
    if re.search(r"integration|connectors|partners", path):
        return "integrations"
    if re.search(r"/blog/?$", path):
        return "blog_index"
    # Posts live under /blog/..., or (e.g. cognee.ai) as a top-level hyphenated slug.
    if "/blog/" in path or re.fullmatch(r"/[a-z0-9]+(-[a-z0-9]+){2,}", path):
        return "blog_post"
    return "product"


def clean_text(markup: str) -> tuple[str, str]:
    soup = BeautifulSoup(markup, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""
    for tag in soup(STRIP_TAGS):
        tag.decompose()
    node = soup.find("main") or soup.find(attrs={"role": "main"}) or soup.find("article") or soup.body or soup
    text = re.sub(r"\s+", " ", node.get_text(" ", strip=True))
    return title, text[:MAX_CHARS]


def html_to_text(markup: str) -> str:
    soup = BeautifulSoup(html.unescape(markup or ""), "html.parser")
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True))[:MAX_CHARS]


def get(url: str):
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException as e:
        print(f"  skip {url} ({type(e).__name__})")
        return None
    if r.status_code != 200:
        print(f"  skip {url} (HTTP {r.status_code})")
        return None
    return r


def job_score(title: str) -> int:
    if EXCLUDE_RE.search(title) or not ROLE_RE.search(title):
        return -1
    return 1 + len(BOOST_RE.findall(title))


def fetch_jobs(seed: dict) -> list[dict]:
    """Return candidate jobs as {title, url, text}, best first."""
    jobs = []
    if seed.get("greenhouse"):
        r = get(f"https://boards-api.greenhouse.io/v1/boards/{seed['greenhouse']}/jobs?content=true")
        if r:
            for j in r.json().get("jobs", []):
                jobs.append({"title": j.get("title", ""), "url": j.get("absolute_url", ""),
                             "text": html_to_text(j.get("content", ""))})
    if seed.get("ashby"):
        r = get(f"https://api.ashbyhq.com/posting-api/job-board/{seed['ashby']}")
        if r:
            for j in r.json().get("jobs", []):
                if j.get("isListed") is False:
                    continue
                text = (j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml", "")))[:MAX_CHARS]
                jobs.append({"title": j.get("title", ""), "url": j.get("jobUrl", ""), "text": text})
    scored = [(job_score(j["title"]), j) for j in jobs if j["url"]]
    scored = [s for s in scored if s[0] > 0]
    scored.sort(key=lambda s: -s[0])
    return [j for _, j in scored[:JOBS_PER_COMPANY]]


def write(path: Path, url: str, title: str, ptype: str, text: str):
    path.write_text(json.dumps({"url": url, "title": title, "page_type": ptype, "text": text}, indent=2))


def crawl_company(key: str, seed: dict, refresh: bool) -> list[str]:
    out_dir = RAW / key
    out_dir.mkdir(parents=True, exist_ok=True)
    types = []
    urls = seed.get("urls", [])
    for n, url in enumerate(urls, 1):
        path = out_dir / f"{n}.json"
        if path.exists() and not refresh:
            types.append(json.loads(path.read_text())["page_type"])
            continue
        r = get(url)
        if not r:
            continue
        title, text = clean_text(r.text)
        ptype = page_type(url, seed["home"])
        write(path, url, title, ptype, text)
        types.append(ptype)

    # Jobs are numbered after the pages.
    job_paths = [out_dir / f"{len(urls) + i}.json" for i in (1, 2)]
    if all(p.exists() for p in job_paths) and not refresh:
        types += [json.loads(p.read_text())["page_type"] for p in job_paths]
    elif seed.get("greenhouse") or seed.get("ashby"):
        for path, job in zip(job_paths, fetch_jobs(seed)):
            write(path, job["url"], job["title"], "job", job["text"])
            types.append("job")
    return types


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-fetch even if cached")
    args = ap.parse_args()

    seeds = json.loads(SEEDS.read_text())
    rows = []
    for key, seed in seeds.items():
        print(f"{key}:")
        rows.append((key, crawl_company(key, seed, args.refresh)))

    print(f"\n{'company':<13}{'pages':>6}  page types")
    print("-" * 70)
    for key, types in rows:
        counts = Counter(types)
        print(f"{key:<13}{len(types):>6}  " + ", ".join(f"{t}×{c}" if c > 1 else t for t, c in counts.items()))


if __name__ == "__main__":
    main()
