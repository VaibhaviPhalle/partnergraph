from typing import Literal

from pydantic import BaseModel, Field


class Signal(BaseModel):
    problem_id: str
    type: Literal["job", "blog", "product", "integration", "other"]
    quote: str = Field(max_length=200)  # verbatim from the page
    source_url: str


class ProblemRef(BaseModel):
    id: str
    label: str


class CompanyProfile(BaseModel):
    key: str
    name: str
    url: str
    capabilities: list[str] = []
    problems_solved: list[ProblemRef] = []
    segments: list[str] = []
    tech_stack: list[str] = []
    integrations: list[str] = []
    signals: list[Signal] = []


class Evidence(BaseModel):
    claim: str
    source_url: str


class Match(BaseModel):
    target_key: str
    customer_score: int
    partner_score: int
    type: Literal["customer", "partner", "both"]
    evidence: list[Evidence] = []
    explanation: str = ""
    # Not in the original spec: records how the explanation was produced.
    explanation_source: Literal["cognee", "fallback", "none"] = "none"
