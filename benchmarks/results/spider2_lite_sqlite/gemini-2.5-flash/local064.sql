WITH MonthlyBalances AS (
    SELECT
        customer_id,
        strftime('%Y-%m', txn_date) AS month_year,
        SUM(CASE
            WHEN txn_type = 'deposit' THEN txn_amount
            WHEN txn_type = 'withdrawal' THEN -txn_amount
            ELSE 0
        END) AS month_end_balance
    FROM
        main.customer_transactions
    WHERE
        strftime('%Y', txn_date) = '2020'
    GROUP BY
        customer_id,
        month_year
),
PositiveBalanceCounts AS (
    SELECT
        month_year,
        COUNT(customer_id) AS positive_balance_customer_count
    FROM
        MonthlyBalances
    WHERE
        month_end_balance > 0
    GROUP BY
        month_year
),
MaxMinMonths AS (
    SELECT
        (SELECT month_year FROM PositiveBalanceCounts ORDER BY positive_balance_customer_count DESC, month_year ASC LIMIT 1) AS max_count_month,
        (SELECT month_year FROM PositiveBalanceCounts ORDER BY positive_balance_customer_count ASC, month_year ASC LIMIT 1) AS min_count_month
),
AverageBalancesForSelectedMonths AS (
    SELECT
        mb.month_year,
        AVG(mb.month_end_balance) AS average_balance
    FROM
        MonthlyBalances mb
    JOIN
        MaxMinMonths mmm ON mb.month_year = mmm.max_count_month OR mb.month_year = mmm.min_count_month
    GROUP BY
        mb.month_year
)
SELECT
    (SELECT average_balance FROM AverageBalancesForSelectedMonths WHERE month_year = (SELECT max_count_month FROM MaxMinMonths)) -
    (SELECT average_balance FROM AverageBalancesForSelectedMonths WHERE month_year = (SELECT min_count_month FROM MaxMinMonths))