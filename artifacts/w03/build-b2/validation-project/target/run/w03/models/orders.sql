
  
  create view "data"."main"."orders__dbt_tmp" as (
    select * from raw_orders
  );
