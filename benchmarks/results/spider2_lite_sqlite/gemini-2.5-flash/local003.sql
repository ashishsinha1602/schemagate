WITH delivered_orders_payments AS (
    SELECT
        o.customer_id,
        c.customer_unique_id,
        o.order_id,
        o.order_purchase_timestamp,
        SUM(op.payment_value) AS order_total_spend
    FROM main.orders AS o
    JOIN main.customers AS c
        ON o.customer_id = c.customer_id
    JOIN main.order_payments AS op
        ON o.order_id = op.order_id
    WHERE o.order_status = 'delivered'
    GROUP BY
        o.customer_id,
        c.customer_unique_id,
        o.order_id,
        o.order_purchase_timestamp
),
customer_rfm_values AS (
    SELECT
        customer_unique_id,
        MAX(order_purchase_timestamp) AS last_purchase_date,
        COUNT(DISTINCT order_id) AS frequency,
        SUM(order_total_spend) AS monetary,
        SUM(order_total_spend) * 1.0 / COUNT(DISTINCT order_id) AS avg_sales_per_order_customer
    FROM delivered_orders_payments
    GROUP BY customer_unique_id
),
reference_date_cte AS (
    SELECT MAX(order_purchase_timestamp) AS max_purchase_date
    FROM delivered_orders_payments
),
customer_rfm_recency AS (
    SELECT
        cr.customer_unique_id,
        JULIANDAY(rd.max_purchase_date) - JULIANDAY(cr.last_purchase_date) AS recency_days,
        cr.frequency,
        cr.monetary,
        cr.avg_sales_per_order_customer
    FROM customer_rfm_values AS cr
    CROSS JOIN reference_date_cte AS rd
),
customer_rfm_scores AS (
    SELECT
        customer_unique_id,
        NTILE(5) OVER (ORDER BY recency_days ASC) AS r_score,
        NTILE(5) OVER (ORDER BY frequency DESC) AS f_score,
        NTILE(5) OVER (ORDER BY monetary DESC) AS m_score,
        avg_sales_per_order_customer
    FROM customer_rfm_recency
),
customer_rfm_segments AS (
    SELECT
        customer_unique_id,
        r_score,
        f_score,
        m_score,
        (f_score + m_score) AS fm_sum,
        avg_sales_per_order_customer,
        CASE
            WHEN r_score = 1 AND (f_score + m_score) BETWEEN 1 AND 4 THEN 'Champions'
            WHEN r_score IN (4, 5) AND (f_score + m_score) BETWEEN 1 AND 2 THEN 'Can''t Lose Them'
            WHEN r_score IN (4, 5) AND (f_score + m_score) BETWEEN 3 AND 6 THEN 'Hibernating'
            WHEN r_score IN (4, 5) AND (f_score + m_score) BETWEEN 7 AND 10 THEN 'Lost'
            WHEN r_score IN (2, 3) AND (f_score + m_score) BETWEEN 1 AND 4 THEN 'Loyal Customers'
            WHEN r_score = 3 AND (f_score + m_score) BETWEEN 5 AND 6 THEN 'Needs Attention'
            WHEN r_score = 1 AND (f_score + m_score) BETWEEN 7 AND 8 THEN 'Recent Users'
            WHEN (r_score = 1 AND (f_score + m_score) BETWEEN 5 AND 6) OR (r_score = 2 AND (f_score + m_score) BETWEEN 5 AND 8) THEN 'Potential Loyalists'
            WHEN r_score = 1 AND (f_score + m_score) BETWEEN 9 AND 10 THEN 'Price Sensitive'
            WHEN r_score = 2 AND (f_score + m_score) BETWEEN 9 AND 10 THEN 'Promising'
            WHEN r_score = 3 AND (f_score + m_score) BETWEEN 7 AND 10 THEN 'About to Sleep'
            ELSE 'Other'
        END AS rfm_segment
    FROM customer_rfm_scores
)
SELECT
    rfm_segment,
    AVG(avg_sales_per_order_customer) AS average_sales_per_order_segment
FROM customer_rfm_segments
GROUP BY rfm_segment
ORDER BY average_sales_per_order_segment DESC