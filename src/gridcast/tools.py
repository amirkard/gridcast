"""Tools the agent can call. Each returns plain JSON-serialisable data."""

from datetime import date

import pandas as pd
from sqlalchemy import text

from gridcast.db import get_engine

TOOLS = [
    {
        "name": "query_load_history",
        "description": (
        "summary returns min/max/mean over the whole range from raw 15-minute "
        "intervals — use this for any question about a minimum or maximum. "
        "hourly and daily average within each period and will therefore miss "
        "true extremes. "
        "daily returns one row per LOCAL calendar day with a `complete` flag; "
        "rows where complete is false are only partly covered by the requested range "
        "and their min/max are not that day's true extremes"
),
        "input_schema": {
            "type": "object",
            "properties": {
                "start": {"type": "string", "description": "YYYY-MM-DD"},
                "end": {"type": "string", "description": "YYYY-MM-DD, EXCLUSIVE - to cover all of February 2026, pass 2026-03-01"},
                "aggregate": {
                    "type": "string",
                    "enum": ["hourly", "daily", "summary"],
                    "description": "summary returns min/max/mean over the range",
                },
            },
            "required": ["start", "end", "aggregate"],
        },
    },
    {
        "name": "get_forecast",
        "description": (
            "Model prediction of Belgian grid load for upcoming hours, with the "
            "TSO's own published forecast alongside for comparison."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "hours": {"type": "integer", "description": "1 to 168"},
            },
            "required": ["hours"],
        },
    },
    {
        "name": "get_model_info",
        "description": (
            "Accuracy and provenance of the forecasting model: backtest MAPE, "
            "the TSO baseline it was measured against, training window, features."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
]


def query_load_history(start: str, end: str, aggregate: str) -> dict:
    if start == end:
        return {"error": "start and end are equal; end is exclusive, so this range is empty"}
    if aggregate == "summary":
        sql = """
            select count(*) as intervals,
                   round(min(load_mw)::numeric, 1) as min_mw,
                   round(max(load_mw)::numeric, 1) as max_mw,
                   round(avg(load_mw)::numeric, 1) as mean_mw
            from load_actual where ts >= :s and ts < :e
        """
    elif aggregate == "daily":
        sql = """
            select (ts at time zone 'Europe/Brussels')::date as day,
                   count(*) as intervals,
                   count(*) = (
                       extract(epoch from (
                           ((ts at time zone 'Europe/Brussels')::date + 1)::timestamp
                               at time zone 'Europe/Brussels'
                           - (ts at time zone 'Europe/Brussels')::date::timestamp
                               at time zone 'Europe/Brussels'
                       )) / 900
                   )::int as complete,
                   round(min(load_mw)::numeric, 1) as min_mw,
                   round(max(load_mw)::numeric, 1) as max_mw,
                   round(avg(load_mw)::numeric, 1) as mean_mw
            from load_actual where ts >= :s and ts < :e
            group by 1 order by 1 limit 100
        """
    else:
        sql = """
            select date_trunc('hour', ts) as hour,
                   round(avg(load_mw)::numeric, 1) as mean_mw
            from load_actual where ts >= :s and ts < :e
            group by 1 order by 1 limit 400
        """
    with get_engine().connect() as c:
        df = pd.read_sql(text(sql), c, params={"s": start, "e": end})

    if df.empty or (aggregate == "summary" and int(df.iloc[0]["intervals"]) == 0):
        return {"error": f"no measured data between {start} and {end}"}

    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]) or df[col].dtype == object:
            df[col] = df[col].astype(str)

    df = df.where(pd.notna(df), None)
    return {"rows": df.to_dict("records")}


def get_forecast(hours: int) -> dict:
    from gridcast.features import FEATURES, add_calendar
    import joblib
    from pathlib import Path

    hours = max(1, min(hours, 168))
    sql = "select * from forecast_features where ts > now() order by ts limit :n"
    with get_engine().connect() as c:
        df = pd.read_sql(text(sql), c, params={"n": hours * 4})
    df = add_calendar(df).dropna(subset=FEATURES)
    if df.empty:
        return {"error": "no feature rows available"}

    model = joblib.load(Path("models/model.joblib"))
    df["predicted_mw"] = model.predict(df[FEATURES]).round(1)
    out = df[["ts", "predicted_mw", "forecast_da"]].rename(
        columns={"forecast_da": "tso_forecast_mw"}
    )
    out["ts"] = out["ts"].astype(str)
    out = out.where(pd.notna(out), None)
    return {"rows": out.to_dict("records")}


def get_model_info() -> dict:
    import json
    from pathlib import Path

    return json.loads(Path("models/metadata.json").read_text())


DISPATCH = {
    "query_load_history": query_load_history,
    "get_forecast": get_forecast,
    "get_model_info": get_model_info,
}
