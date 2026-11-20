"""Deterministic scoring of each target against the "me" company (MY_COMPANY_KEY). No LLM."""
import os

from models import CompanyProfile, Evidence, Match

OWN_KEY = os.getenv("MY_COMPANY_KEY", "partnergraph")
WEIGHTS = {"job": 3, "blog": 2, "product": 1, "integration": 1}  # "other" counts 0
CUSTOMER_FULL_POINTS = 15  # this many weighted points = score 100 (then capped)


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def _lists(own: CompanyProfile, target: CompanyProfile) -> bool:
    """True if target lists own company in integrations, or own lists the target."""
    own_names = {own.key.lower(), own.name.lower()}
    tgt_names = {target.key.lower(), target.name.lower()}
    if any(o in i for i in target.integrations for o in own_names):
        return True
    return any(t in i for i in own.integrations for t in tgt_names)


def score_target(own: CompanyProfile, target: CompanyProfile) -> Match:
    vocab = {p.id for p in own.problems_solved}
    labels = {p.id: p.label for p in own.problems_solved}

    # ---- customer
    points, evidence = 0, []
    for s in target.signals:
        w = WEIGHTS.get(s.type, 0)
        if s.problem_id in vocab and w:
            points += w
            evidence.append(Evidence(
                claim=f'{target.name} {s.type} signal for "{labels[s.problem_id]}": "{s.quote}"',
                source_url=s.source_url))
    customer = min(100, round(100 * points / CUSTOMER_FULL_POINTS))

    # ---- partner
    partner = 0.0
    if _lists(own, target):
        partner += 40
        evidence.append(Evidence(
            claim=f"{target.name} and {own.name} list each other as an integration/partner",
            source_url=target.url))
    seg_o, seg_t = set(own.segments), set(target.segments)
    seg_j = jaccard(seg_o, seg_t)
    partner += 30 * seg_j
    if seg_o & seg_t:
        evidence.append(Evidence(
            claim=f"Shared segments: {', '.join(sorted(seg_o & seg_t))}", source_url=target.url))
    eco_o = set(own.tech_stack) | set(own.integrations)
    eco_t = set(target.tech_stack) | set(target.integrations)
    shared = eco_o & eco_t
    # overlap ratio = shared / size of the smaller ecosystem
    ratio = len(shared) / min(len(eco_o), len(eco_t)) if eco_o and eco_t else 0.0
    partner += 30 * ratio
    for item in sorted(shared):
        evidence.append(Evidence(
            claim=f"Shared tech/integration: {item}", source_url=target.url))
    partner_i = min(100, round(partner))

    if customer >= 40 and partner_i >= 40:
        mtype = "both"
    else:
        mtype = "customer" if customer >= partner_i else "partner"
    return Match(target_key=target.key, customer_score=customer, partner_score=partner_i,
                 type=mtype, evidence=evidence)


def score_all(profiles: dict[str, CompanyProfile]) -> list[Match]:
    own = profiles[OWN_KEY]
    return [score_target(own, p) for k, p in profiles.items() if k != OWN_KEY]
