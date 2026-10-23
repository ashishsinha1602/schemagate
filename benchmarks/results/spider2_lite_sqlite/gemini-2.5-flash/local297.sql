WITH MonthlyNet AS (
    SELECT
        customer_id,
        strftime('%Y-%m-01', txn_date) AS month_start_date,
        SUM(CASE WHEN txn_type = 'deposit' THEN txn_amount ELSE 0 END) -
        SUM(CASE WHEN txn_type = 'withdrawal' THEN txn_amount ELSE 0 END) AS monthly_net_amount
    FROM
        main.customer_transactions
    GROUP BY
        customer_id,
        month_start_date
),
MonthlyBalance AS (
    SELECT
        customer_id,
        month_start_date,
        SUM(monthly_net_amount) OVER (PARTITION BY customer_id ORDER BY month_start_date) AS closing_balance
    FROM
        MonthlyNet
),
CustomerRecentBalances AS (
    SELECT
        customer_id,
        closing_balance,
        LAG(closing_balance, 1, 0) OVER (PARTITION BY customer_id ORDER BY month_start_date) AS prior_month_balance,
        ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY month_start_date DESC) AS rn
    FROM
        MonthlyBalance
),
CustomerGrowthRates AS (
    SELECT
        customer_id,
        CASE
            WHEN prior_month_balance = 0 THEN closing_balance * 100.0
            ELSE (closing_balance - prior_month_balance) * 100.0 / prior_month_balance
        END AS growth_rate
    FROM
        CustomerRecentBalances
    WHERE
        rn = 1
)
SELECT
    CAST(SUM(CASE WHEN growth_rate > 5 THEN 1 ELSE 0 END) AS REAL) * 100.0 / COUNT(customer_id)
FROM
    CustomerGrowthRates