"""Tool contract tests. These need a populated database."""

import json

import pytest

from gridcast.tools import DISPATCH, TOOLS, get_model_info, query_load_history

KNOWN_RANGE = ("2025-03-01", "2025-03-04")


# --- the bugs that actually happened -----------------------------------------

@pytest.mark.parametrize("aggregate", ["summary", "daily", "hourly"])
def test_result_is_json_serialisable(aggregate):
    """Dates and NaN broke json.dumps twice. Every shape must survive it."""
    out = query_load_history(*KNOWN_RANGE, aggregate)
    json.dumps(out)


def test_empty_range_returns_error_not_nulls():
    """An empty summary aggregate returns one row of NULLs, not zero rows."""
    out = query_load_history("2030-01-01", "2030-01-02", "summary")
    assert "error" in out
    assert "rows" not in out


def test_equal_dates_rejected():
    """end is exclusive, so start == end is an empty range."""
    out = query_load_history("2025-03-01", "2025-03-01", "summary")
    assert "error" in out


def test_no_nan_strings_in_output():
    """astype(str) once turned NULL into the literal string 'nan'."""
    for aggregate in ("summary", "daily", "hourly"):
        text = json.dumps(query_load_history(*KNOWN_RANGE, aggregate))
        assert "nan" not in text.lower()


# --- correctness --------------------------------------------------------------

def test_summary_uses_raw_intervals_not_averages():
    """summary must see the true extremes; hourly averaging hides them."""
    s = query_load_history("2024-07-01", "2024-08-01", "summary")["rows"][0]
    h = query_load_history("2024-07-01", "2024-08-01", "hourly")["rows"]
    assert s["min_mw"] <= min(r["mean_mw"] for r in h)
    assert s["max_mw"] >= max(r["mean_mw"] for r in h)


def test_summary_interval_count_matches_period():
    """Three days at 15-minute resolution is 288 intervals."""
    out = query_load_history(*KNOWN_RANGE, "summary")["rows"][0]
    assert out["intervals"] == 288


def test_load_values_are_physically_plausible():
    out = query_load_history(*KNOWN_RANGE, "summary")["rows"][0]
    assert 3000 < out["min_mw"] < out["mean_mw"] < out["max_mw"] < 20000


def test_daily_flags_partial_days():
    """UTC ranges span an extra local day; boundary days must be flagged."""
    rows = query_load_history(*KNOWN_RANGE, "daily")["rows"]
    assert len({r["day"] for r in rows}) == len(rows)
    assert sum(r["intervals"] for r in rows) == 288
    assert not rows[0]["complete"]
    assert not rows[-1]["complete"]
    assert all(r["complete"] for r in rows[1:-1])


def test_dst_days_count_as_complete():
    """Spring forward gives 92 intervals, fall back 100. Both are full days."""
    spring = query_load_history("2025-03-29", "2025-03-31", "daily")["rows"]
    autumn = query_load_history("2025-10-25", "2025-10-27", "daily")["rows"]
    days = {r["day"]: r for r in spring + autumn}
    assert days["2025-03-30"]["intervals"] == 92
    assert days["2025-03-30"]["complete"]
    assert days["2025-10-26"]["intervals"] == 100
    assert days["2025-10-26"]["complete"]


# --- the schema the model depends on ------------------------------------------

def test_every_tool_has_a_dispatch_entry():
    assert {t["name"] for t in TOOLS} == set(DISPATCH)


def test_tool_schemas_are_well_formed():
    for tool in TOOLS:
        assert tool["description"].strip()
        schema = tool["input_schema"]
        assert schema["type"] == "object"
        for field in schema.get("required", []):
            assert field in schema["properties"], f"{tool['name']}: {field}"


def test_metadata_states_the_conclusion_not_just_numbers():
    """The week-4 hallucination came from metadata without an interpretation."""
    ev = get_model_info()["evaluation"]
    for key in ("ci95_pp", "p_value", "conclusion", "caveat"):
        assert key in ev, f"missing {key}"
    assert "not" in ev["conclusion"].lower()
