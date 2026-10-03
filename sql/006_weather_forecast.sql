create table if not exists weather_forecast (
    ts          timestamptz not null,
    temp_c      double precision,
    fetched_at  timestamptz not null default now(),
    primary key (ts)
);
