WITH cat_pay AS (
  SELECT p.product_category_name AS category,
         op.payment_type,
         COUNT(*) AS payment_count
  FROM olist_order_items oi
  JOIN olist_products p ON p.product_id = oi.product_id
  JOIN olist_order_payments op ON op.order_id = oi.order_id
  GROUP BY p.product_category_name, op.payment_type
),
ranked AS (
  SELECT category, payment_type, payment_count,
         ROW_NUMBER() OVER (PARTITION BY category ORDER BY payment_count DESC) AS rn
  FROM cat_pay
)
SELECT AVG(payment_count) AS avg_top_payment_count
FROM ranked
WHERE rn = 1