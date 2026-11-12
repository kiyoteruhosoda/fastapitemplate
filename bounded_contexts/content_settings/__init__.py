"""Content settings (per-tenant rules for content; ADR-0084 §3, ADR-0085).

The code (``domain/definitions.py``) holds the item definitions; the DB holds the values per tenant.
Items not saved read as the definition's default.
"""
