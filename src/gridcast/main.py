from datetime import date, timedelta

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="Gridcast", version="0.1.0")


class HealthResponse(BaseModel):
    status: str
    version: str


class ForecastPoint(BaseModel):
    target_date: date
    load_mw: float = Field(description="Forecast load in megawatts")


class ForecastResponse(BaseModel):
    zone: str
    model: str
    points: list[ForecastPoint]


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=app.version)


@app.get("/forecast", response_model=ForecastResponse)
def forecast(zone: str = "BE", days: int = 3) -> ForecastResponse:
    today = date.today()
    points = [
        ForecastPoint(target_date=today + timedelta(days=i + 1), load_mw=9000.0)
        for i in range(days)
    ]
    return ForecastResponse(zone=zone, model="stub-constant", points=points)
