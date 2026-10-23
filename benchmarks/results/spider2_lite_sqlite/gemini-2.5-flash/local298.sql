WITH customer_transaction_amounts AS (
    SELECT
        customer_id,
        txn_date,
        CASE
            WHEN txn_type = 'deposit' THEN txn_amount
            ELSE -txn_amount
        END AS effective_amount
    FROM main.customer_transactions
),
customer_running_balances AS (
    SELECT
        customer_id,
        txn_date,
        SUM(effective_amount) OVER (PARTITION BY customer_id ORDER BY txn_date) AS running_balance
    FROM customer_transaction_amounts
),
all_months AS (
    SELECT DISTINCT STRFTIME('%Y-%m', txn_date) AS month_str
    FROM main.customer_transactions
),
all_customers AS (
    SELECT DISTINCT customer_id
    FROM main.customer_transactions
),
customer_month_combinations AS (
    SELECT
        ac.customer_id,
        am.month_str
    FROM all_customers ac
    CROSS JOIN all_months am
),
customer_balance_at_month_end AS (
    SELECT
        cmc.customer_id,
        cmc.month_str,
        (
            SELECT crb.running_balance
            FROM customer_running_balances crb
            WHERE crb.customer_id = cmc.customer_id
              AND STRFTIME('%Y-%m', crb.txn_date) <= cmc.month_str
            ORDER BY crb.txn_date DESC
            LIMIT 1
        ) AS eom_balance_raw
    FROM customer_month_combinations cmc
),
customer_eom_balances_filled AS (
    SELECT
        customer_id,
        month_str AS month,
        COALESCE(eom_balance_raw, 0) AS eom_balance
    FROM customer_balance_at_month_end
),
monthly_total_balances AS (
    SELECT
        month,
        SUM(eom_balance) AS total_eom_balance
    FROM customer_eom_balances_filled
    GROUP BY month
),
lagged_balances AS (
    SELECT
        month,
        LAG(total_eom_balance) OVER (ORDER BY month) AS previous_month_total_balance
    FROM monthly_total_balances
)
SELECT
    month,
    MAX(0, previous_month_total_balance) AS previous_month_total_balance
FROM lagged_balances
WHERE previous_month_total_balance IS NOT NULL
ORDER BY month