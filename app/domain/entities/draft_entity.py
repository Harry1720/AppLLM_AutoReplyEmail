from dataclasses import dataclass
from typing import Optional

@dataclass
class DraftEntity:
    id: str
    user_id: str
    email_id: str
    thread_id: str
    draft_id: str
    subject: str
    body: str
    recipient: str
    status: str = "draft"