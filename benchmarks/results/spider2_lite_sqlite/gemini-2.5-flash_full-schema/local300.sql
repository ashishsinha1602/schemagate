WITH RECURSIVE DateSeries AS (
    -- Anchor member: Get the minimum and maximum transaction dates for each customer
    SELECT
        customer_id,
        MIN(txn_date) AS current_date,
        MAX(txn_date) AS max_date
    FROM main.customer_transactions
    GROUP BY customer_id

    UNION ALL

    -- Recursive member: Generate all dates between min_date and max_date for each customer
    SELECT
        customer_id,
        DATE(current_date, '+1 day'),
        max_date
    FROM DateSeries
    WHERE current_date < max_date
),
DailyTransactionChanges AS (
    -- Calculate the net change in balance for each customer on each transaction date
    SELECT
        customer_id,
        txn_date,
        SUM(CASE
            WHEN txn_type = 'deposit' THEN txn_amount
            ELSE -txn_amount
        END) AS daily_net_change
    FROM main.customer_transactions
    GROUP BY customer_id, txn_date
),
CustomerDailyBalancesRaw AS (
    -- Combine all generated dates with daily transaction changes
    -- Calculate the running balance for each customer, carrying forward previous day's balance
    SELECT
        ds.customer_id,
        ds.current_date AS balance_date,
        COALESCE(dtc.daily_net_change, 0) AS daily_change_for_date,
        SUM(COALESCE(dtc.daily_net_change, 0)) OVER (PARTITION BY ds.customer_id ORDER BY ds.current_date) AS running_balance_cumulative
    FROM DateSeries ds
    LEFT JOIN DailyTransactionChanges dtc
        ON ds.customer_id = dtc.customer_id AND ds.current_date = dtc.txn_date
),
CustomerDailyBalances AS (
    -- Apply the condition: treat any negative daily balances as zero
    SELECT
        customer_id,
        balance_date,
        MAX(0, running_balance_cumulative) AS daily_balance
    FROM CustomerDailyBalancesRaw
),
MonthlyHighestBalances AS (
    -- For each customer, determine the highest daily balance during each month
    SELECT
        customer_id,
        STRFTIME('%Y-%m', balance_date) AS month,
        MAX(daily_balance) AS highest_daily_balance_in_month
    FROM CustomerDailyBalances
    GROUP BY customer_id, STRFTIME('%Y-%m', balance_date)
)
-- Final step: For each month, sum these maximum daily balances across all customers
SELECT
    month,
    SUM(highest_daily_balance_in_month) AS total_monthly_highest_balance
FROM MonthlyHighestBalances
GROUP BY month
ORDER BY month