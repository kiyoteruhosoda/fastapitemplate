from dataclasses import dataclass


@dataclass(frozen=True)
class ItemName:
    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("Item name cannot be empty")
        if len(self.value) > 255:
            raise ValueError("Item name cannot exceed 255 characters")
