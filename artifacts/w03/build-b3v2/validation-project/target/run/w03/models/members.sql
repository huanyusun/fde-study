
  
  create view "data"."main"."members__dbt_tmp" as (
    select * from raw_members
  );
