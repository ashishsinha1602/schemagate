WITH cp AS (
  SELECT DISTINCT pr.product_category_name AS cat, p.order_id, p.payment_sequential, p.payment_type
  FROM main.olist_order_payments p
  JOIN main.olist_order_items i ON i.order_id = p.order_id
  JOIN main.olist_products pr ON pr.product_id = i.product_id
  WHERE pr.product_category_name IS NOT NULL
),
cnt AS (
  SELECT cat, payment_type, COUNT(*) AS n
  FROM cp
  GROUP BY cat, payment_type
),
ranked AS (
  SELECT cat, payment_type, n, ROW_NUMBER() OVER (PARTITION BY cat ORDER BY n DESC) AS rn
  FROM cnt
)
SELECT AVG(n) AS avg_top_payment_method_count
FROM ranked
WHERE rn = 1