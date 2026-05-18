from pydantic import BaseModel


class LivenessResponse(BaseModel):
    status: str
    version: str
    timestamp_utc: str
    uptime_seconds: float


class ReadinessResponse(BaseModel):
    status: str
    # key = check name, value = "ok" | "ng"
    # Add new checks here as the system grows (e.g. "cache", "external_api")
    checks: dict[str, str]
    timestamp_utc: str


class InfoResponse(BaseModel):
    version: str
    git_sha: str
    build_time: str
    environment: str
