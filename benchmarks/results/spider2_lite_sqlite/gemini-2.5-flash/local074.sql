WITH distinct_customers AS (
    SELECT DISTINCT customer_id
    FROM main.customer_transactions
),
distinct_months AS (
    SELECT DISTINCT strftime('%Y-%m', txn_date) AS month
    FROM main.customer_transactions
),
all_customer_month_combinations AS (
    SELECT
        dc.customer_id,
        dm.month
    FROM
        distinct_customers AS dc
    CROSS JOIN
        distinct_months AS dm
),
monthly_transactions AS (
    SELECT
        customer_id,
        strftime('%Y-%m', txn_date) AS month,
        SUM(CASE
            WHEN txn_type = 'deposit' THEN txn_amount
            ELSE -txn_amount
        END) AS net_transaction_amount
    FROM
        main.customer_transactions
    GROUP BY
        customer_id,
        month
),
customer_monthly_activity AS (
    SELECT
        acmc.customer_id,
        acmc.month,
        COALESCE(mt.net_transaction_amount, 0) AS monthly_net_amount
    FROM
        all_customer_month_combinations AS acmc
    LEFT JOIN
        monthly_transactions AS mt
        ON acmc.customer_id = mt.customer_id
        AND acmc.month = mt.month
),
calculated_balances AS (
    SELECT
        customer_id,
        month,
        monthly_net_amount,
        SUM(monthly_net_amount) OVER (PARTITION BY customer_id ORDER BY month) AS closing_balance
    FROM
        customer_monthly_activity
)
SELECT
    customer_id,
    month,
    closing_balance,
    closing_balance - LAG(closing_balance, 1, 0) OVER (PARTITION BY customer_id ORDER BY month) AS monthly_change
FROM
    calculated_balances
ORDER BY
    customer_id,
    month