WITH DailyNetBalance AS (
    SELECT
        customer_id,
        txn_date,
        SUM(CASE
            WHEN txn_type = 'deposit' THEN txn_amount
            ELSE -txn_amount
        END) AS net_amount_on_day
    FROM main.customer_transactions
    GROUP BY
        customer_id,
        txn_date
),
CustomerDailyRunningBalance AS (
    SELECT
        customer_id,
        txn_date,
        SUM(net_amount_on_day) OVER (PARTITION BY customer_id ORDER BY txn_date) AS daily_running_balance
    FROM DailyNetBalance
),
RollingAverage AS (
    SELECT
        customer_id,
        txn_date,
        CASE
            WHEN COUNT(daily_running_balance) OVER (PARTITION BY customer_id ORDER BY txn_date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) >= 30
            THEN MAX(0, AVG(daily_running_balance) OVER (PARTITION BY customer_id ORDER BY txn_date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW))
            ELSE NULL
        END AS rolling_avg_balance_30_day
    FROM CustomerDailyRunningBalance
),
CustomerMonthlyMaxRollingAvg AS (
    SELECT
        customer_id,
        STRFTIME('%Y-%m', txn_date) AS txn_month,
        MAX(rolling_avg_balance_30_day) AS max_monthly_rolling_avg
    FROM RollingAverage
    WHERE rolling_avg_balance_30_day IS NOT NULL
    GROUP BY
        customer_id,
        STRFTIME('%Y-%m', txn_date)
),
FirstTransactionMonth AS (
    SELECT
        customer_id,
        STRFTIME('%Y-%m', MIN(txn_date)) AS first_month
    FROM main.customer_transactions
    GROUP BY
        customer_id
)
SELECT
    T1.txn_month,
    SUM(T1.max_monthly_rolling_avg) AS total_sum_max_rolling_avg
FROM CustomerMonthlyMaxRollingAvg AS T1
JOIN FirstTransactionMonth AS T2
    ON T1.customer_id = T2.customer_id
WHERE T1.txn_month != T2.first_month
GROUP BY
    T1.txn_month
ORDER BY
    T1.txn_month