WITH MidJuneWeek AS (
    SELECT DISTINCT
        calendar_year,
        (SELECT week_number FROM main.cleaned_weekly_sales
         WHERE T1.calendar_year = calendar_year
           AND '06-15' BETWEEN STRFTIME('%m-%d', week_date_formatted) AND STRFTIME('%m-%d', DATE(week_date_formatted, '+6 days'))
         LIMIT 1) AS mid_june_week_number
    FROM main.cleaned_weekly_sales AS T1
    WHERE calendar_year IN (2018, 2019, 2020)
),
SalesPeriods AS (
    SELECT
        cws.calendar_year,
        SUM(CASE
            WHEN cws.week_number IN (mjw.mid_june_week_number - 4, mjw.mid_june_week_number - 3, mjw.mid_june_week_number - 2, mjw.mid_june_week_number - 1)
            THEN cws.sales
            ELSE 0
        END) AS sales_before_mid_june,
        SUM(CASE
            WHEN cws.week_number IN (mjw.mid_june_week_number + 1, mjw.mid_june_week_number + 2, mjw.mid_june_week_number + 3, mjw.mid_june_week_number + 4)
            THEN cws.sales
            ELSE 0
        END) AS sales_after_mid_june
    FROM main.cleaned_weekly_sales AS cws
    JOIN MidJuneWeek AS mjw
        ON cws.calendar_year = mjw.calendar_year
    WHERE cws.calendar_year IN (2018, 2019, 2020)
    GROUP BY cws.calendar_year
)
SELECT
    calendar_year,
    sales_before_mid_june,
    sales_after_mid_june,
    CASE
        WHEN sales_before_mid_june = 0 THEN NULL
        ELSE (CAST(sales_after_mid_june AS REAL) - sales_before_mid_june) * 100.0 / sales_before_mid_june
    END AS percentage_change
FROM SalesPeriods