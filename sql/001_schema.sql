create table if not exists load_raw (
    ts            timestamptz not null,
    resolution    text,
    load_mw       double precision,
    forecast_da   double precision,
    ingested_at   timestamptz not null default now(),
    primary key (ts)
);

create index if not exists load_raw_ts_idx on load_raw (ts);
