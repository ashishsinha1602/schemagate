WITH MonthlyNet AS (
    SELECT
        customer_id,
        strftime('%Y-%m-01', txn_date) AS month_start,
        SUM(CASE
                WHEN txn_type = 'deposit' THEN txn_amount
                WHEN txn_type = 'withdrawal' THEN -txn_amount
                ELSE 0
            END) AS monthly_net_amount
    FROM main.customer_transactions
    GROUP BY
        customer_id,
        month_start
),
MonthlyBalance AS (
    SELECT
        customer_id,
        month_start,
        monthly_net_amount,
        SUM(monthly_net_amount) OVER (PARTITION BY customer_id ORDER BY month_start) AS closing_balance
    FROM MonthlyNet
),
CustomerMonthlyGrowth AS (
    SELECT
        customer_id,
        month_start,
        closing_balance,
        LAG(closing_balance, 1, 0) OVER (PARTITION BY customer_id ORDER BY month_start) AS previous_month_balance,
        ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY month_start DESC) AS rn
    FROM MonthlyBalance
),
RecentMonthGrowth AS (
    SELECT
        customer_id,
        closing_balance AS current_month_balance,
        previous_month_balance,
        CASE
            WHEN previous_month_balance = 0 THEN closing_balance * 100.0 -- Corrected: Use original column name 'closing_balance'
            ELSE (closing_balance - previous_month_balance) * 100.0 / previous_month_balance -- Corrected: Use original column name 'closing_balance'
        END AS growth_rate
    FROM CustomerMonthlyGrowth
    WHERE rn = 1
)
SELECT
    CAST(SUM(CASE WHEN growth_rate > 5 THEN 1 ELSE 0 END) AS REAL) * 100.0 / COUNT(DISTINCT customer_id)
FROM RecentMonthGrowth