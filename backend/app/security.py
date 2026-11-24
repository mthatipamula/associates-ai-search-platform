"""Document-level security (DLS) for search.

Every query - keyword, vector, RAG and every agent tool call - is built with
an `allowed_groups` filter derived from the caller's identity. The filter is
applied inside Elasticsearch (including as a kNN *pre-filter*), so restricted
content never leaves the cluster and never reaches the LLM prompt.

Production options, in order of preference:
 1. Elasticsearch native DLS: a role with a templated query, e.g.
    {"terms": {"allowed_groups": "{{_user.metadata.groups}}"}}, and the API
    calls ES with the end user's identity (run_as / token service).
 2. This app-level filter, with the identity taken from a verified SSO token.
Either way, permissions are synced from the source system (SharePoint, DMS,
CRM) at ingest time and kept fresh by incremental ACL updates.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Header, HTTPException

from .config import settings


@dataclass(frozen=True)
class User:
    name: str
    groups: tuple[str, ...]


def acl_filter(user: User) -> dict:
    return {"terms": {"allowed_groups": list(user.groups)}}


def client_groups(user: User) -> list[str]:
    """The client teams a user is staffed on (groups named client-<slug>)."""
    return [g for g in user.groups if g.startswith("client-")]


def resolve_user(name: str | None) -> User:
    name = name or "associate"
    profile = settings.demo_users.get(name)
    if profile is None:
        raise HTTPException(status_code=403, detail=f"unknown demo user {name!r}")
    return User(name=name, groups=tuple(profile["groups"]))


def current_user(x_demo_user: str | None = Header(default=None)) -> User:
    """FastAPI dependency. Demo only: production verifies a JWT from SSO."""
    return resolve_user(x_demo_user)
