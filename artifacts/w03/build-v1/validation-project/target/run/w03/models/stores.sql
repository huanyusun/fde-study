
  
  create view "data"."main"."stores__dbt_tmp" as (
    select * from raw_stores
  );
