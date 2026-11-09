
  
  create view "data"."main"."time_spine__dbt_tmp" as (
    select cast(date_day as date) as date_day from generate_series(date '2024-09-01', date '2026-09-01' - interval 1 day, interval 1 day) as t(date_day)
  );
