WITH category_payment_counts AS (
  SELECT
    T2.product_category_name,
    T3.payment_type,
    COUNT(T3.order_id) AS payment_count
  FROM main.olist_order_items AS T1
  INNER JOIN main.olist_products AS T2
    ON T1.product_id = T2.product_id
  INNER JOIN main.olist_order_payments AS T3
    ON T1.order_id = T3.order_id
  GROUP BY
    T2.product_category_name,
    T3.payment_type
), ranked_payment_methods AS (
  SELECT
    product_category_name,
    payment_type,
    payment_count,
    ROW_NUMBER() OVER (PARTITION BY product_category_name ORDER BY payment_count DESC) AS rnk
  FROM category_payment_counts
)
SELECT
  AVG(payment_count)
FROM ranked_payment_methods
WHERE
  rnk = 1