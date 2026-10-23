WITH daily_transactions AS (
    SELECT
        customer_id,
        txn_date,
        SUM(CASE
            WHEN txn_type = 'deposit' THEN txn_amount
            ELSE -txn_amount
        END) AS daily_net_amount
    FROM main.customer_transactions
    GROUP BY
        customer_id,
        txn_date
),
running_balance AS (
    SELECT
        customer_id,
        txn_date,
        SUM(daily_net_amount) OVER (PARTITION BY customer_id ORDER BY txn_date) AS current_balance
    FROM daily_transactions
),
rolling_avg_balance AS (
    SELECT
        customer_id,
        txn_date,
        CAST(strftime('%Y-%m', txn_date) AS TEXT) AS transaction_month,
        MAX(0, AVG(current_balance) OVER (
            PARTITION BY customer_id
            ORDER BY txn_date
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        )) AS rolling_30_day_avg_balance,
        COUNT(current_balance) OVER (
            PARTITION BY customer_id
            ORDER BY txn_date
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        ) AS days_in_window
    FROM running_balance
),
customer_monthly_max_avg AS (
    SELECT
        customer_id,
        transaction_month,
        MAX(rolling_30_day_avg_balance) AS max_monthly_30_day_avg
    FROM rolling_avg_balance
    WHERE days_in_window >= 30
    GROUP BY
        customer_id,
        transaction_month
),
customer_first_month AS (
    SELECT
        customer_id,
        CAST(strftime('%Y-%m', MIN(txn_date)) AS TEXT) AS first_transaction_month
    FROM main.customer_transactions
    GROUP BY
        customer_id
)
SELECT
    cma.transaction_month,
    SUM(cma.max_monthly_30_day_avg) AS total_summed_max_avg_balance
FROM customer_monthly_max_avg cma
JOIN customer_first_month cfm
    ON cma.customer_id = cfm.customer_id
WHERE cma.transaction_month != cfm.first_transaction_month
GROUP BY
    cma.transaction_month
ORDER BY
    cma.transaction_month