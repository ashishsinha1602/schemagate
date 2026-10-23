WITH seller_stats AS (
  SELECT seller_id,
         COUNT(*) AS total_items_sold,
         SUM(price) AS total_sales,
         AVG(price) AS avg_item_price
  FROM order_items
  GROUP BY seller_id
  HAVING COUNT(*) > 100
),
seller_orders AS (
  SELECT DISTINCT seller_id, order_id
  FROM order_items
),
review_stats AS (
  SELECT so.seller_id, AVG(r.review_score) AS avg_review_score
  FROM seller_orders so
  JOIN order_reviews r ON r.order_id = so.order_id
  GROUP BY so.seller_id
),
packing_stats AS (
  SELECT so.seller_id,
         AVG(julianday(o.order_delivered_carrier_date) - julianday(o.order_purchase_timestamp)) AS avg_packing_days
  FROM seller_orders so
  JOIN orders o ON o.order_id = so.order_id
  WHERE o.order_delivered_carrier_date IS NOT NULL
    AND o.order_purchase_timestamp IS NOT NULL
  GROUP BY so.seller_id
),
category_counts AS (
  SELECT oi.seller_id,
         COALESCE(t.product_category_name_english, p.product_category_name) AS category_english,
         COUNT(*) AS items_sold,
         SUM(oi.price) AS category_sales
  FROM order_items oi
  JOIN products p ON p.product_id = oi.product_id
  LEFT JOIN product_category_name_translation t ON t.product_category_name = p.product_category_name
  GROUP BY oi.seller_id, COALESCE(t.product_category_name_english, p.product_category_name)
),
top_category AS (
  SELECT seller_id, category_english, items_sold, category_sales,
         ROW_NUMBER() OVER (PARTITION BY seller_id ORDER BY items_sold DESC, category_sales DESC, category_english) AS rn
  FROM category_counts
)
SELECT s.seller_id,
       sl.seller_city,
       sl.seller_state,
       s.total_items_sold,
       s.total_sales,
       s.avg_item_price,
       rs.avg_review_score,
       ps.avg_packing_days,
       tc.category_english AS top_category_english,
       tc.items_sold AS top_category_items_sold
FROM seller_stats s
LEFT JOIN sellers sl ON sl.seller_id = s.seller_id
LEFT JOIN review_stats rs ON rs.seller_id = s.seller_id
LEFT JOIN packing_stats ps ON ps.seller_id = s.seller_id
LEFT JOIN top_category tc ON tc.seller_id = s.seller_id AND tc.rn = 1
ORDER BY s.total_sales DESC