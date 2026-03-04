"""
Sudoku Ultra — ML Service

FastAPI application providing:
- Difficulty classification (ML-based)
- CV-based puzzle scanning
- RAG-powered technique tutor
- RL bot opponent inference

Full implementation in later phases.
"""

import os
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(
    title="Sudoku Ultra ML Service",
    description="ML/AI microservice for Sudoku Ultra",
    version="0.0.1",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    timestamp: str


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="ml-service",
        version="0.0.1",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "3003"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
