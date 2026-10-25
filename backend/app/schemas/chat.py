from typing import List, Optional
from pydantic import BaseModel, Field, model_validator


class SourceCitation(BaseModel):
    title: str
    url: Optional[str] = None
    document_name: Optional[str] = None
    academic_year: Optional[str] = None
    publication_date: Optional[str] = None
    snippet: Optional[str] = None
    verification_status: Optional[str] = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: Optional[str] = Field(default=None, max_length=64)


class ChatResponse(BaseModel):
    reply: str
    sources: List[SourceCitation] = Field(default_factory=list)
    session_id: Optional[str] = None
    answer: Optional[str] = None

    @model_validator(mode="after")
    def sync_answer_and_reply(self) -> "ChatResponse":
        if not self.answer and self.reply:
            self.answer = self.reply
        elif not self.reply and self.answer:
            self.reply = self.answer
        return self
