WITH pc AS (
  SELECT p.product_category_name AS cat,
         op.payment_type,
         COUNT(DISTINCT op.order_id || '-' || op.payment_sequential) AS n
  FROM olist_order_payments op
  JOIN olist_order_items oi ON oi.order_id = op.order_id
  JOIN olist_products p ON p.product_id = oi.product_id
  WHERE p.product_category_name IS NOT NULL
  GROUP BY p.product_category_name, op.payment_type
),
ranked AS (
  SELECT cat, payment_type, n,
         ROW_NUMBER() OVER (PARTITION BY cat ORDER BY n DESC) AS rn
  FROM pc
)
SELECT COALESCE(t.product_category_name_english, r.cat) AS category,
       r.payment_type,
       r.n AS number_of_payments
FROM ranked r
LEFT JOIN product_category_name_translation t ON t.product_category_name = r.cat
WHERE r.rn = 1
ORDER BY r.n DESC
LIMIT 3