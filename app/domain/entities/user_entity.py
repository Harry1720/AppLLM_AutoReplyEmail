from dataclasses import dataclass
from typing import Optional 

@dataclass
class UserEntity:
    id: str
    email: str
    name: str
    picture: str
    google_refresh_token: Optional[str] = None 
    google_access_token: Optional[str] = None