WITH delivered_items AS (
  SELECT oi.seller_id, oi.order_id, oi.price, oi.freight_value, c.customer_unique_id
  FROM olist_order_items oi
  JOIN olist_orders o ON o.order_id = oi.order_id
  JOIN olist_customers c ON c.customer_id = o.customer_id
  WHERE o.order_status = 'delivered'
),
seller_stats AS (
  SELECT seller_id,
         COUNT(DISTINCT customer_unique_id) AS distinct_customers,
         SUM(price - freight_value) AS profit,
         COUNT(DISTINCT order_id) AS distinct_orders
  FROM delivered_items
  GROUP BY seller_id
),
seller_five_star AS (
  SELECT d.seller_id, COUNT(DISTINCT r.review_id) AS five_star_ratings
  FROM (SELECT DISTINCT seller_id, order_id FROM delivered_items) d
  JOIN olist_order_reviews r ON r.order_id = d.order_id
  WHERE r.review_score = 5
  GROUP BY d.seller_id
)
SELECT * FROM (
  SELECT 'Highest number of distinct customers' AS achievement, seller_id, distinct_customers AS value
  FROM seller_stats ORDER BY distinct_customers DESC LIMIT 1
)
UNION ALL
SELECT * FROM (
  SELECT 'Highest profit' AS achievement, seller_id, profit AS value
  FROM seller_stats ORDER BY profit DESC LIMIT 1
)
UNION ALL
SELECT * FROM (
  SELECT 'Highest number of distinct orders' AS achievement, seller_id, distinct_orders AS value
  FROM seller_stats ORDER BY distinct_orders DESC LIMIT 1
)
UNION ALL
SELECT * FROM (
  SELECT 'Most 5-star ratings' AS achievement, seller_id, five_star_ratings AS value
  FROM seller_five_star ORDER BY five_star_ratings DESC LIMIT 1
)