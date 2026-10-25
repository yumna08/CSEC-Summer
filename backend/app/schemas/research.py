from typing import List, Optional

from pydantic import BaseModel, Field


class ResearchRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=1000)


class ResearchStep(BaseModel):
    question: str
    status: str
    evidence_count: int = 0
    sources: List[str] = Field(default_factory=list)


class ResearchCitation(BaseModel):
    title: str
    url: Optional[str] = None
    academic_year: Optional[str] = None
    subquestion: str


class ResearchResponse(BaseModel):
    summary: str
    steps: List[ResearchStep] = Field(default_factory=list)
    required_documents: List[str] = Field(default_factory=list)
    contacts: List[str] = Field(default_factory=list)
    citations: List[ResearchCitation] = Field(default_factory=list)
    unsupported_or_missing_items: List[str] = Field(default_factory=list)
