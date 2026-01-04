from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid

class DocumentEntity(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: str
    metadata: Dict[str, Any]
    embedding: List[float]
    user_id: str

    class Config:
        from_attributes = True