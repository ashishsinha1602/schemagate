WITH base AS (
  SELECT c.customer_unique_id,
         COUNT(DISTINCT o.order_id) AS order_count,
         SUM(oi.price) AS total_spend,
         MAX(o.order_purchase_timestamp) AS last_purchase
  FROM orders o
  JOIN customers c ON c.customer_id = o.customer_id
  JOIN order_items oi ON oi.order_id = o.order_id
  WHERE o.order_status = 'delivered'
  GROUP BY c.customer_unique_id
),
rec AS (
  SELECT customer_unique_id, order_count, total_spend,
         julianday((SELECT MAX(last_purchase) FROM base)) - julianday(last_purchase) AS recency_days
  FROM base
),
scored AS (
  SELECT customer_unique_id, order_count, total_spend,
         NTILE(5) OVER (ORDER BY recency_days ASC) AS r,
         NTILE(5) OVER (ORDER BY order_count DESC) AS f,
         NTILE(5) OVER (ORDER BY total_spend DESC) AS m
  FROM rec
),
segmented AS (
  SELECT customer_unique_id, order_count, total_spend,
         total_spend * 1.0 / order_count AS avg_sales_per_order,
         CASE
           WHEN r = 1 AND f + m BETWEEN 1 AND 4 THEN 'Champions'
           WHEN r IN (4,5) AND f + m BETWEEN 1 AND 2 THEN 'Can''t Lose Them'
           WHEN r IN (4,5) AND f + m BETWEEN 3 AND 6 THEN 'Hibernating'
           WHEN r IN (4,5) AND f + m BETWEEN 7 AND 10 THEN 'Lost'
           WHEN r IN (2,3) AND f + m BETWEEN 1 AND 4 THEN 'Loyal Customers'
           WHEN r = 3 AND f + m BETWEEN 5 AND 6 THEN 'Needs Attention'
           WHEN r = 1 AND f + m BETWEEN 7 AND 8 THEN 'Recent Users'
           WHEN (r = 1 AND f + m BETWEEN 5 AND 6) OR (r = 2 AND f + m BETWEEN 5 AND 8) THEN 'Potential Loyalists'
           WHEN r = 1 AND f + m BETWEEN 9 AND 10 THEN 'Price Sensitive'
           WHEN r = 2 AND f + m BETWEEN 9 AND 10 THEN 'Promising'
           WHEN r = 3 AND f + m BETWEEN 7 AND 10 THEN 'About to Sleep'
         END AS rfm_segment
  FROM scored
)
SELECT rfm_segment,
       COUNT(*) AS customers,
       SUM(total_spend) AS segment_total_spend,
       SUM(order_count) AS segment_total_orders,
       AVG(avg_sales_per_order) AS avg_sales_per_order_per_customer,
       SUM(total_spend) * 1.0 / SUM(order_count) AS segment_avg_sales_per_order
FROM segmented
WHERE rfm_segment IS NOT NULL
GROUP BY rfm_segment
ORDER BY avg_sales_per_order_per_customer DESC