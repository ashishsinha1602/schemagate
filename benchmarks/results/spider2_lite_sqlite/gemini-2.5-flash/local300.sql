WITH RECURSIVE DateSeries AS (
    SELECT
        MIN(txn_date) AS dt
    FROM main.customer_transactions
    UNION ALL
    SELECT
        DATE(dt, '+1 day')
    FROM DateSeries
    WHERE dt < (SELECT MAX(txn_date) FROM main.customer_transactions)
),
CustomerDateRange AS (
    SELECT
        customer_id,
        MIN(txn_date) AS first_txn_date,
        MAX(txn_date) AS last_txn_date
    FROM main.customer_transactions
    GROUP BY customer_id
),
AllCustomerDates AS (
    SELECT
        cdr.customer_id,
        ds.dt AS current_date
    FROM CustomerDateRange cdr
    JOIN DateSeries ds ON ds.dt BETWEEN cdr.first_txn_date AND cdr.last_txn_date
),
DailyTransactionAggregates AS (
    SELECT
        customer_id,
        txn_date,
        SUM(CASE
            WHEN txn_type = 'deposit' THEN txn_amount
            ELSE -txn_amount
        END) AS net_change
    FROM main.customer_transactions
    GROUP BY customer_id, txn_date
),
DailyBalancesWithGaps AS (
    SELECT
        acd.customer_id,
        acd.current_date,
        COALESCE(dta.net_change, 0) AS daily_net_change
    FROM AllCustomerDates acd
    LEFT JOIN DailyTransactionAggregates dta
        ON acd.customer_id = dta.customer_id AND acd.current_date = dta.txn_date
),
DailyBalances AS (
    SELECT
        customer_id,
        current_date,
        MAX(0, SUM(daily_net_change) OVER (PARTITION BY customer_id ORDER BY current_date)) AS daily_balance
    FROM DailyBalancesWithGaps
),
MonthlyMaxDailyBalance AS (
    SELECT
        customer_id,
        STRFTIME('%Y-%m', current_date) AS month_year,
        MAX(daily_balance) AS max_daily_balance_in_month
    FROM DailyBalances
    GROUP BY customer_id, month_year
)
SELECT
    month_year,
    SUM(max_daily_balance_in_month) AS total_monthly_max_balance
FROM MonthlyMaxDailyBalance
GROUP BY month_year
ORDER BY month_year