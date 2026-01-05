from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class DraftEntity(BaseModel):
    user_id: str
    email_id: str
    thread_id: str
    draft_id: str
    
    subject: Optional[str] = None
    body: Optional[str] = None
    recipient: Optional[str] = None
    status: str = "draft"
    created_at: Optional[str] = None 
    id: Optional[str] = None 

    class Config:
        from_attributes = True