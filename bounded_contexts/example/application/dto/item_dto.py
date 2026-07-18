from dataclasses import dataclass


@dataclass(frozen=True)
class ItemDTO:
    id: int
    name: str
