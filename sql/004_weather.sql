create table if not exists weather_raw (
    ts          timestamptz not null,
    temp_c      double precision,
    ingested_at timestamptz not null default now(),
    primary key (ts)
);
