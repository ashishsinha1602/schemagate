WITH delivered AS (
    SELECT o.order_id,
           c.customer_unique_id,
           o.order_purchase_timestamp
    FROM orders o
    JOIN customers c ON c.customer_id = o.customer_id
    WHERE o.order_status = 'delivered'
),
pay AS (
    SELECT order_id, SUM(payment_value) AS order_value
    FROM order_payments
    GROUP BY order_id
),
cust AS (
    SELECT d.customer_unique_id,
           MAX(d.order_purchase_timestamp) AS last_purchase_ts,
           COUNT(DISTINCT d.order_id) AS total_orders,
           SUM(COALESCE(p.order_value, 0)) AS total_spend
    FROM delivered d
    LEFT JOIN pay p ON p.order_id = d.order_id
    GROUP BY d.customer_unique_id
),
ref AS (
    SELECT MAX(order_purchase_timestamp) AS max_ts
    FROM delivered
),
scored AS (
    SELECT c.customer_unique_id,
           c.total_orders,
           c.total_spend,
           julianday(r.max_ts) - julianday(c.last_purchase_ts) AS recency_days,
           NTILE(5) OVER (ORDER BY julianday(r.max_ts) - julianday(c.last_purchase_ts) ASC) AS r_score,
           NTILE(5) OVER (ORDER BY c.total_orders DESC) AS f_score,
           NTILE(5) OVER (ORDER BY c.total_spend DESC) AS m_score
    FROM cust c
    CROSS JOIN ref r
),
segmented AS (
    SELECT s.*,
           CASE
               WHEN r_score = 1 AND f_score + m_score BETWEEN 1 AND 4 THEN 'Champions'
               WHEN r_score IN (4, 5) AND f_score + m_score BETWEEN 1 AND 2 THEN 'Can''t Lose Them'
               WHEN r_score IN (4, 5) AND f_score + m_score BETWEEN 3 AND 6 THEN 'Hibernating'
               WHEN r_score IN (4, 5) AND f_score + m_score BETWEEN 7 AND 10 THEN 'Lost'
               WHEN r_score IN (2, 3) AND f_score + m_score BETWEEN 1 AND 4 THEN 'Loyal Customers'
               WHEN r_score = 3 AND f_score + m_score BETWEEN 5 AND 6 THEN 'Needs Attention'
               WHEN r_score = 1 AND f_score + m_score BETWEEN 7 AND 8 THEN 'Recent Users'
               WHEN (r_score = 1 AND f_score + m_score BETWEEN 5 AND 6)
                 OR (r_score = 2 AND f_score + m_score BETWEEN 5 AND 8) THEN 'Potential Loyalists'
               WHEN r_score = 1 AND f_score + m_score BETWEEN 9 AND 10 THEN 'Price Sensitive'
               WHEN r_score = 2 AND f_score + m_score BETWEEN 9 AND 10 THEN 'Promising'
               WHEN r_score = 3 AND f_score + m_score BETWEEN 7 AND 10 THEN 'About to Sleep'
           END AS rfm_segment
    FROM scored s
)
SELECT rfm_segment,
       COUNT(*) AS customers,
       SUM(total_orders) AS total_orders,
       ROUND(SUM(total_spend), 2) AS total_spend,
       ROUND(SUM(total_spend) / SUM(total_orders), 2) AS avg_sales_per_order,
       ROUND(AVG(total_spend * 1.0 / total_orders), 2) AS mean_customer_avg_sales_per_order,
       ROUND(AVG(recency_days), 1) AS avg_recency_days
FROM segmented
GROUP BY rfm_segment
ORDER BY avg_sales_per_order DESC