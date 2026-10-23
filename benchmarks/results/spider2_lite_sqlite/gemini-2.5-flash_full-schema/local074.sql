WITH monthly_transactions AS (
    SELECT
        customer_id,
        strftime('%Y-%m', txn_date) AS month_year,
        SUM(CASE
            WHEN txn_type = 'deposit' THEN txn_amount
            ELSE -txn_amount
        END) AS monthly_net_change
    FROM main.customer_transactions
    GROUP BY
        customer_id,
        strftime('%Y-%m', txn_date)
),
distinct_customers AS (
    SELECT DISTINCT customer_id
    FROM main.customer_transactions
),
distinct_months AS (
    SELECT DISTINCT strftime('%Y-%m', txn_date) AS month_year
    FROM main.customer_transactions
),
all_customer_months AS (
    SELECT
        dc.customer_id,
        dm.month_year
    FROM distinct_customers AS dc
    CROSS JOIN distinct_months AS dm
),
monthly_balances_with_gaps AS (
    SELECT
        acm.customer_id,
        acm.month_year,
        COALESCE(mt.monthly_net_change, 0) AS monthly_change
    FROM all_customer_months AS acm
    LEFT JOIN monthly_transactions AS mt
        ON acm.customer_id = mt.customer_id
        AND acm.month_year = mt.month_year
)
SELECT
    customer_id,
    month_year,
    monthly_change,
    SUM(monthly_change) OVER (PARTITION BY customer_id ORDER BY month_year) AS cumulative_balance
FROM monthly_balances_with_gaps
ORDER BY
    customer_id,
    month_year