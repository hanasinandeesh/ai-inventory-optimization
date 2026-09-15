from pydantic import BaseModel, Field


class HealthCheckResponse(BaseModel):
    status: str = Field(..., description="Overall service status ('ok' or 'error')")
    version: str = Field(..., description="Application version")
    environment: str = Field(..., description="Runtime environment")
    database: str = Field(
        ..., description="Database connection status ('connected' or 'disconnected')"
    )

