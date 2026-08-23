# src/lumneo/memory/model/user_directive.py
from datetime import datetime
from typing import Literal, Optional
from dataclasses import dataclass

from lumneo.memory.common.time import utc_now

@dataclass
class UserDirective:
    type: Literal["forget", "do_not_remember", "temporary", "correct"]
    target: Optional[str] = None
    target_type: Optional[Literal["memory_id", "semantic_match", "predicate_match"]] = None
    scope: Optional[str] = None
    raw_text: str = ""
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = utc_now()