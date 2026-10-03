create or replace view load_features as
select
    ts,
    load_mw,
    forecast_da,
    lag(load_mw, 192) over w  as lag_2d,
    lag(load_mw, 288) over w  as lag_3d,
    lag(load_mw, 672) over w  as lag_7d,
    lag(load_mw, 1344) over w as lag_14d,
    avg(load_mw) over (order by ts rows between 1535 preceding and 192 preceding)
        as roll_mean_14d,
    stddev(load_mw) over (order by ts rows between 1535 preceding and 192 preceding)
        as roll_std_14d
from load_actual
window w as (order by ts);
