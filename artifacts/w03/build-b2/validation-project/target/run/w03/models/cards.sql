
  
  create view "data"."main"."cards__dbt_tmp" as (
    select * from raw_cards
  );
