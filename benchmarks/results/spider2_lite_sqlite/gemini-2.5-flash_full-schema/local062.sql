WITH CustomerProfits AS (
    SELECT
        p.cust_id,
        SUM((p.unit_price - p.unit_cost) * p.quantity_sold) AS total_profit
    FROM
        profits AS p
    JOIN
        times AS t ON p.time_id = t.time_id
    JOIN
        customers AS c ON p.cust_id = c.cust_id
    JOIN
        countries AS co ON c.country_id = co.country_id
    WHERE
        t.calendar_year = 2021
        AND t.calendar_month_number = 12
        AND co.country_name = 'Italy'
    GROUP BY
        p.cust_id
),
OverallProfitStats AS (
    SELECT
        MIN(total_profit) AS min_overall_profit,
        MAX(total_profit) AS max_overall_profit
    FROM
        CustomerProfits
),
BucketsData AS (
    SELECT
        cp.cust_id,
        cp.total_profit,
        ops.min_overall_profit,
        ops.max_overall_profit,
        CASE
            WHEN (ops.max_overall_profit - ops.min_overall_profit) = 0 THEN 1.0 -- Avoid division by zero if all profits are identical
            ELSE (ops.max_overall_profit - ops.min_overall_profit) / 10.0
        END AS interval_size
    FROM
        CustomerProfits AS cp,
        OverallProfitStats AS ops
)
SELECT
    'Bucket ' || (
        CASE
            WHEN bd.interval_size = 0 THEN 1 -- All customers have the same profit, put them in Bucket 1
            WHEN bd.total_profit = bd.max_overall_profit THEN 10 -- Ensure the max value falls into the last bucket
            ELSE CAST(FLOOR((bd.total_profit - bd.min_overall_profit) / bd.interval_size) AS INTEGER) + 1
        END
    ) AS profit_bucket,
    COUNT(bd.cust_id) AS number_of_customers,
    MIN(bd.total_profit) AS min_profit_in_bucket,
    MAX(bd.total_profit) AS max_profit_in_bucket
FROM
    BucketsData AS bd
GROUP BY
    profit_bucket
ORDER BY
    MIN(bd.total_profit)