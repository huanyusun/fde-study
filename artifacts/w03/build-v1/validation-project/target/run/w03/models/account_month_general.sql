
  
  create view "data"."main"."account_month_general__dbt_tmp" as (
    select cast(month_start as varchar) || '|' || member_id as account_month_key, member_id, month_start, valid_order_cnt from (select member_id, date_trunc('month', ordered_at) as month_start, count(*) as valid_order_cnt from "data"."main"."orders" where status = 'paid' and paid_cents - refund_cents > 0 group by member_id, date_trunc('month', ordered_at))
  );
