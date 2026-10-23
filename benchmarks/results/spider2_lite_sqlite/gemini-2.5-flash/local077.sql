WITH MonthlyIndexComposition AS (
    SELECT
        _year,
        _month,
        month_year,
        interest_id,
        composition / index_value AS index_composition
    FROM
        main.interest_metrics
    WHERE
        (_year = 2018 AND _month >= 9) OR (_year = 2019 AND _month <= 8)
),
RankedMonthlyComposition AS (
    SELECT
        _year,
        _month,
        month_year,
        interest_id,
        index_composition,
        ROW_NUMBER() OVER (PARTITION BY _year, _month ORDER BY index_composition DESC) as rn
    FROM
        MonthlyIndexComposition
),
MonthlyMaxInterest AS (
    SELECT
        _year,
        _month,
        month_year,
        interest_id,
        index_composition AS max_index_composition
    FROM
        RankedMonthlyComposition
    WHERE
        rn = 1
),
MonthlyTopInterestData AS (
    SELECT
        mmi._year,
        mmi._month,
        mmi.month_year,
        im.interest_name,
        mmi.max_index_composition
    FROM
        MonthlyMaxInterest mmi
    JOIN
        main.interest_map im ON mmi.interest_id = im.id
)
SELECT
    mtd.month_year AS date,
    mtd.interest_name,
    mtd.max_index_composition,
    AVG(mtd.max_index_composition) OVER (ORDER BY mtd._year, mtd._month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS rolling_avg,
    LAG(mtd.interest_name, 1) OVER (ORDER BY mtd._year, mtd._month) AS prev_month_interest_name,
    LAG(mtd.max_index_composition, 1) OVER (ORDER BY mtd._year, mtd._month) AS prev_month_max_index_composition,
    LAG(mtd.interest_name, 2) OVER (ORDER BY mtd._year, mtd._month) AS two_prev_month_interest_name,
    LAG(mtd.max_index_composition, 2) OVER (ORDER BY mtd._year, mtd._month) AS two_prev_month_max_index_composition
FROM
    MonthlyTopInterestData mtd
ORDER BY
    mtd._year, mtd._month