from pydantic import BaseModel, Field, ConfigDict
from typing import Any, Dict, Optional

class RuleCreate(BaseModel):
    keyword: str = Field(min_length=1, max_length=200)
    dm_message: str = Field(min_length=1, max_length=5000)

class RuleResponse(BaseModel):
    rule_id: str
    keyword: str
    dm_message: str

class WebhookData(BaseModel):
    model_config = ConfigDict(extra="allow")
    comment_id: str
    post_id: Optional[str] = None
    text: Optional[str] = None
    created_at: Optional[str] = None
    from_: Optional[Dict[str, Any]] = Field(default=None, alias="from")

class WebhookEvent(BaseModel):
    model_config = ConfigDict(extra="allow")
    event_id: str
    event_type: str
    sent_at: Optional[str] = None
    data: WebhookData

class StatsResponse(BaseModel):
    sent: int
    failed: int
    queued: int
    duplicates_blocked: int
