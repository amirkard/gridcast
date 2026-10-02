-- Measured history: the only rows valid for training and evaluation.
create or replace view load_actual as
select ts, resolution, load_mw, forecast_da
from load_raw
where load_mw is not null;

-- Published forecasts for periods that have not happened yet.
create or replace view load_future as
select ts, forecast_da
from load_raw
where load_mw is null and ts > now();
