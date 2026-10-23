WITH MonthlyBalancesRaw AS (
    SELECT
        customer_id,
        STRFTIME('%Y-%m', txn_date) AS transaction_month,
        SUM(CASE
            WHEN txn_type = 'deposit' THEN txn_amount
            WHEN txn_type = 'withdrawal' THEN -txn_amount
            ELSE 0
        END) AS balance_change_for_month
    FROM
        main.customer_transactions
    WHERE
        STRFTIME('%Y', txn_date) = '2020'
    GROUP BY
        customer_id,
        transaction_month
),
AllCustomers2020 AS (
    SELECT DISTINCT customer_id
    FROM main.customer_transactions
    WHERE STRFTIME('%Y', txn_date) = '2020'
),
AllMonths2020 AS (
    SELECT '2020-01' AS month UNION ALL
    SELECT '2020-02' UNION ALL
    SELECT '2020-03' UNION ALL
    SELECT '2020-04' UNION ALL
    SELECT '2020-05' UNION ALL
    SELECT '2020-06' UNION ALL
    SELECT '2020-07' UNION ALL
    SELECT '2020-08' UNION ALL
    SELECT '2020-09' UNION ALL
    SELECT '2020-10' UNION ALL
    SELECT '2020-11' UNION ALL
    SELECT '2020-12'
),
CustomerMonthCombinations AS (
    SELECT
        ac.customer_id,
        am.month AS transaction_month
    FROM
        AllCustomers2020 ac
    CROSS JOIN
        AllMonths2020 am
),
MonthlyBalances AS (
    SELECT
        cmc.customer_id,
        cmc.transaction_month,
        COALESCE(mbr.balance_change_for_month, 0) AS month_end_balance
    FROM
        CustomerMonthCombinations cmc
    LEFT JOIN
        MonthlyBalancesRaw mbr ON cmc.customer_id = mbr.customer_id
                               AND cmc.transaction_month = mbr.transaction_month
),
MonthlySummary AS (
    SELECT
        transaction_month,
        COUNT(DISTINCT CASE WHEN month_end_balance > 0 THEN customer_id END) AS positive_balance_customers_count,
        AVG(month_end_balance) AS average_month_end_balance_all_customers
    FROM
        MonthlyBalances
    GROUP BY
        transaction_month
),
RankedMonths AS (
    SELECT
        transaction_month,
        positive_balance_customers_count,
        average_month_end_balance_all_customers,
        RANK() OVER (ORDER BY positive_balance_customers_count DESC) AS rank_highest,
        RANK() OVER (ORDER BY positive_balance_customers_count ASC) AS rank_lowest
    FROM
        MonthlySummary
),
HighestMonth AS (
    SELECT
        transaction_month AS highest_month,
        average_month_end_balance_all_customers AS avg_balance_highest_month
    FROM
        RankedMonths
    WHERE
        rank_highest = 1
    ORDER BY transaction_month
    LIMIT 1
),
LowestMonth AS (
    SELECT
        transaction_month AS lowest_month,
        average_month_end_balance_all_customers AS avg_balance_lowest_month
    FROM
        RankedMonths
    WHERE
        rank_lowest = 1
    ORDER BY transaction_month
    LIMIT 1
)
SELECT
    hm.highest_month,
    hm.avg_balance_highest_month,
    lm.lowest_month,
    lm.avg_balance_lowest_month,
    hm.avg_balance_highest_month - lm.avg_balance_lowest_month AS difference_in_avg_balances
FROM
    HighestMonth hm,
    LowestMonth lm