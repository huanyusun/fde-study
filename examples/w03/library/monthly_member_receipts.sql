WITH base AS (
  SELECT
    member_id,
    DATE_TRUNC('month', ordered_at) AS month_start,
    SUM(paid_cents - refund_cents) AS net_receipts_cents
  FROM {{ ref('orders') }}
  WHERE status = 'paid'
  GROUP BY member_id, DATE_TRUNC('month', ordered_at)
)
SELECT
  member_id,
  month_start,
  net_receipts_cents,
  member_id || '|' || CAST(month_start AS VARCHAR) AS member_month_key
FROM base