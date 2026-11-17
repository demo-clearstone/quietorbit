from __future__ import annotations

from pydantic import BaseModel, Field


class ValidationItem(BaseModel):
    code: str
    label: str
    passed: bool
    detail: str = ""
    page: int | None = None


class ReviewResult(BaseModel):
    items: list[ValidationItem] = Field(default_factory=list)
    ssn_found: bool = False
    ssn_pages: list[int] = Field(default_factory=list)


class RuleDecision(BaseModel):
    rule_id: str
    section: str
    action: str
    reason: str
    skipped: bool = False
