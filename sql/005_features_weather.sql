create or replace view load_features as
with w as (
    select ts,
           temp_c,
           avg(temp_c) over (order by ts rows between 23 preceding and current row)
               as temp_24h_mean
    from weather_raw
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
    w.temp_c,
    w.temp_24h_mean,
    greatest(0, 16.5 - w.temp_c) as hdd,
    greatest(0, w.temp_c - 18.0) as cdd
from load_actual l
left join w on w.ts = date_trunc('hour', l.ts)
window o as (order by l.ts);
