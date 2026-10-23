WITH category_payment_counts AS (
  SELECT
    pct.product_category_name_english,
    op.payment_type,
    COUNT(op.payment_type) AS payment_count
  FROM main.olist_order_items AS oi
  JOIN main.olist_products AS p
    ON oi.product_id = p.product_id
  JOIN main.product_category_name_translation AS pct
    ON p.product_category_name = pct.product_category_name
  JOIN main.olist_order_payments AS op
    ON oi.order_id = op.order_id
  GROUP BY
    pct.product_category_name_english,
    op.payment_type
), ranked_payment_methods AS (
  SELECT
    product_category_name_english,
    payment_count,
    ROW_NUMBER() OVER (PARTITION BY product_category_name_english ORDER BY payment_count DESC) AS rn
  FROM category_payment_counts
)
SELECT
  AVG(payment_count)
FROM ranked_payment_methods
WHERE
  rn = 1