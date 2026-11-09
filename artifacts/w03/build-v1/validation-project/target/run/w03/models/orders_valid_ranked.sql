
  
  create view "data"."main"."orders_valid_ranked__dbt_tmp" as (
    select order_id, member_id, ordered_at, paid_cents - refund_cents as net_cents, row_number() over (partition by member_id order by ordered_at, order_id) as first_seq from "data"."main"."orders" where status = 'paid' and paid_cents - refund_cents > 0
  );
