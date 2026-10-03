-- Features for every timestamp on the grid, including future ones.
-- Lags and rolling windows end 192 slots (48 h) before the target, so they
-- always reach back into measured history.
create or replace view forecast_features as
with w as (
    -- Measured temperature where available, forecast temperature beyond it.
    select coalesce(a.ts, f.ts) as ts,
           coalesce(a.temp_c, f.temp_c) as temp_c
    from weather_raw a
    full outer join weather_forecast f on f.ts = a.ts
),
wx as (
    select ts,
           temp_c,
           avg(temp_c) over (order by ts rows between 23 preceding and current row)
               as temp_24h_mean
    from w
)
select
    l.ts,
    l.load_mw,
    l.forecast_da,
    lag(l.load_mw, 192)  over o as lag_2d,
    lag(l.load_mw, 288)  over o as lag_3d,
    lag(l.load_mw, 672)  over o as lag_7d,
    lag(l.load_mw, 1344) over o as lag_14d,
    avg(l.load_mw) over (order by l.ts rows between 1535 preceding and 192 preceding)
        as roll_mean_14d,
    stddev(l.load_mw) over (order by l.ts rows between 1535 preceding and 192 preceding)
        as roll_std_14d,
    wx.temp_c,
    wx.temp_24h_mean,
    greatest(0, 16.5 - wx.temp_c) as hdd,
    greatest(0, wx.temp_c - 18.0) as cdd
from load_raw l
left join wx on wx.ts = date_trunc('hour', l.ts)
window o as (order by l.ts);
