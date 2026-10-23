WITH AllMonths AS (
    SELECT DISTINCT STRFTIME('%Y-%m', txn_date) AS month_str
    FROM main.customer_transactions
),
AllCustomerMonths AS (
    SELECT
        c.customer_id,
        am.month_str
    FROM (SELECT DISTINCT customer_id FROM main.customer_transactions) AS c
    CROSS JOIN AllMonths AS am
),
MonthlyTransactions AS (
    SELECT
        customer_id,
        STRFTIME('%Y-%m', txn_date) AS transaction_month,
        SUM(CASE
            WHEN txn_type = 'deposit' THEN txn_amount
            WHEN txn_type = 'purchase' THEN -txn_amount
            WHEN txn_type = 'withdrawal' THEN -txn_amount
            ELSE 0
        END) AS monthly_change
    FROM main.customer_transactions
    GROUP BY
        customer_id,
        transaction_month
),
CustomerMonthlyActivity AS (
    SELECT
        acm.customer_id,
        acm.month_str AS transaction_month,
        COALESCE(mt.monthly_change, 0) AS monthly_change
    FROM AllCustomerMonths AS acm
    LEFT JOIN MonthlyTransactions AS mt
        ON acm.customer_id = mt.customer_id
        AND acm.month_str = mt.transaction_month
    ORDER BY
        acm.customer_id,
        acm.month_str
),
CustomerRunningBalance AS (
    SELECT
        customer_id,
        transaction_month,
        SUM(monthly_change) OVER (
            PARTITION BY customer_id
            ORDER BY transaction_month ASC
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_balance
    FROM CustomerMonthlyActivity
),
LaggedCustomerBalance AS (
    SELECT
        customer_id,
        transaction_month,
        LAG(running_balance, 1, 0) OVER (
            PARTITION BY customer_id
            ORDER BY transaction_month ASC
        ) AS previous_month_balance
    FROM CustomerRunningBalance
),
MinOverallMonth AS (
    SELECT MIN(month_str) AS first_month
    FROM AllMonths
)
SELECT
    LCB.transaction_month,
    SUM(MAX(0, LCB.previous_month_balance)) AS total_previous_month_balance
FROM LaggedCustomerBalance AS LCB
CROSS JOIN MinOverallMonth AS MOM
WHERE LCB.transaction_month > MOM.first_month
GROUP BY
    LCB.transaction_month
ORDER BY
    LCB.transaction_month ASC