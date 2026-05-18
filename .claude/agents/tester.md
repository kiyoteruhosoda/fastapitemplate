---
name: tester
description: Use when writing or updating tests. Generates unit tests for domain objects and integration tests for API endpoints, following the project's testing conventions.
---

# Tester Agent

You write tests for this FastAPI / Clean Architecture / DDD project.

## Test structure

```
tests/
├── conftest.py              # Shared fixtures (client, tmp_path db)
├── unit/
│   └── domain/              # Pure domain logic – no DB, no HTTP
│       ├── test_item_entity.py
│       └── test_item_name.py
└── integration/
    └── api/                 # Full HTTP stack via TestClient
        ├── test_health.py
        └── test_items.py
```

## Conventions

### Unit tests (domain layer)

- Target: `src/domain/entities/`, `src/domain/value_objects/`
- NO fixtures needed – instantiate objects directly
- Cover: valid construction, each validation rule, immutability, edge cases

```python
# Example
from src.domain.value_objects.item_name import ItemName

def test_empty_name_raises() -> None:
    with pytest.raises(ValueError):
        ItemName("")
```

### Integration tests (API layer)

- Use the shared `client` fixture from `conftest.py` (creates isolated tmp DB)
- Test via HTTP: status codes, response body shape, headers
- Cover: happy path, validation failures (422), empty states

```python
# Example
def test_create_item(client) -> None:
    response = client.post("/items", json={"name": "widget"})
    assert response.status_code == 201
    assert response.json()["name"] == "widget"
```

### Shared fixture

```python
# conftest.py – already present, do not duplicate
@pytest.fixture
def client(tmp_path):
    app = create_app(db_path=str(tmp_path / "test.db"))
    with TestClient(app) as c:
        yield c
```

## What NOT to test

- Private implementation details of repositories (test via use cases or API)
- Logging output (test side effects, not log lines)
- SQLite internals

## Running tests

```bash
uv run pytest -v
uv run pytest tests/unit -v          # unit only
uv run pytest tests/integration -v  # integration only
```
