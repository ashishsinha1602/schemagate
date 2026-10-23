WITH base AS (
  SELECT oi.seller_id, oi.order_id, oi.order_item_id, oi.price, oi.freight_value, c.customer_unique_id
  FROM olist_order_items oi
  JOIN olist_orders o ON o.order_id = oi.order_id AND o.order_status = 'delivered'
  JOIN olist_customers c ON c.customer_id = o.customer_id
),
so AS (
  SELECT DISTINCT seller_id, order_id FROM base
)
SELECT * FROM (
  SELECT 'Highest number of distinct customer unique IDs' AS achievement, seller_id, COUNT(DISTINCT customer_unique_id) AS value
  FROM base
  GROUP BY seller_id
  ORDER BY value DESC, seller_id
  LIMIT 1
)
UNION ALL
SELECT * FROM (
  SELECT 'Highest profit (price minus freight value)' AS achievement, seller_id, SUM(price - freight_value) AS value
  FROM base
  GROUP BY seller_id
  ORDER BY value DESC, seller_id
  LIMIT 1
)
UNION ALL
SELECT * FROM (
  SELECT 'Highest number of distinct orders' AS achievement, seller_id, COUNT(DISTINCT order_id) AS value
  FROM base
  GROUP BY seller_id
  ORDER BY value DESC, seller_id
  LIMIT 1
)
UNION ALL
SELECT * FROM (
  SELECT 'Most 5-star ratings' AS achievement, so.seller_id, COUNT(*) AS value
  FROM so
  JOIN olist_order_reviews r ON r.order_id = so.order_id AND r.review_score = 5
  GROUP BY so.seller_id
  ORDER BY value DESC, so.seller_id
  LIMIT 1
)