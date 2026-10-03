import json
import os
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from gridcast.features import FEATURES, add_calendar

import joblib
import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text

from gridcast.features import FEATURES

load_dotenv()
DB = os.environ["DATABASE_URL"]
MODEL_DIR = Path("models")

state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    state["engine"] = create_engine(DB, pool_pre_ping=True, pool_size=5)
    state["model"] = joblib.load(MODEL_DIR / "model.joblib")
    state["meta"] = json.loads((MODEL_DIR / "metadata.json").read_text())
    yield
    state["engine"].dispose()


app = FastAPI(title="Gridcast", version="0.2.0", lifespan=lifespan)


class HealthResponse(BaseModel):
    status: str
    version: str
    model_version: str | None = None
    latest_measurement: datetime | None = None


class ForecastPoint(BaseModel):
    ts: datetime
    predicted_mw: float
    tso_forecast_mw: float | None = Field(
        None, description="The TSO's own published day-ahead forecast"
    )


class ForecastResponse(BaseModel):
    model_version: str
    generated_at: datetime
    points: list[ForecastPoint]


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    with state["engine"].connect() as c:
        latest = c.execute(
            text("select max(ts) from load_actual")
        ).scalar_one_or_none()
    return HealthResponse(
        status="ok",
        version=app.version,
        model_version=state["meta"]["version"],
        latest_measurement=latest,
    )


@app.get("/history")
def history(start: date, end: date, limit: int = 2000) -> list[dict]:
    sql = text("""
        select ts, load_mw, forecast_da
        from load_actual
        where ts >= :start and ts < :end
        order by ts
        limit :limit
    """)
    with state["engine"].connect() as c:
        rows = c.execute(sql, {"start": start, "end": end, "limit": limit})
        return [dict(r._mapping) for r in rows]


@app.get("/forecast", response_model=ForecastResponse)
def forecast(hours: int = 24) -> ForecastResponse:
    if not 1 <= hours <= 168:
        raise HTTPException(400, "hours must be between 1 and 168")

    sql = text("""
        select * from forecast_features
        where ts > now()
        order by ts
        limit :n
    """)
    with state["engine"].connect() as c:
        df = pd.read_sql(sql, c, params={"n": hours * 4})

    if df.empty:
        raise HTTPException(
            503, "no feature rows available for future timestamps"
        )


    df = add_calendar(df)
    df = df.dropna(subset=FEATURES)

    if df.empty:
        raise HTTPException(503, "feature rows incomplete for the requested horizon")

    preds = state["model"].predict(df[FEATURES])
    return ForecastResponse(
        model_version=state["meta"]["version"],
        generated_at=datetime.now(),
        points=[
            ForecastPoint(
                ts=row.ts,
                predicted_mw=round(float(p), 1),
                tso_forecast_mw=(
                    None if pd.isna(row.forecast_da) else float(row.forecast_da)
                ),
            )
            for row, p in zip(df.itertuples(), preds)
        ],
    )
