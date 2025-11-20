from dataclasses import dataclass

@dataclass
class UserEntity:
    id: str
    email: str
    name: str
    picture: str
