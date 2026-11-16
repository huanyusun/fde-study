select cast(date_day as date) as date_day from generate_series(date '{{ var("coverage_start") }}', date '{{ var("coverage_end") }}' - interval 1 day, interval 1 day) as t(date_day)
