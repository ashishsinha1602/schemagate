WITH SalesPeriods AS (
    SELECT
        calendar_year,
        SUM(CASE WHEN week_number BETWEEN 20 AND 23 THEN sales ELSE 0 END) AS sales_before_mid_june,
        SUM(CASE WHEN week_number BETWEEN 25 AND 28 THEN sales ELSE 0 END) AS sales_after_mid_june
    FROM
        main.cleaned_weekly_sales
    WHERE
        calendar_year IN (2018, 2019, 2020)
        AND week_number BETWEEN 20 AND 28
    GROUP BY
        calendar_year
)
SELECT
    calendar_year,
    sales_before_mid_june,
    sales_after_mid_june,
    CASE
        WHEN sales_before_mid_june = 0 THEN NULL
        ELSE ROUND(((CAST(sales_after_mid_june AS REAL) - sales_before_mid_june) / sales_before_mid_june) * 100, 2)
    END AS percentage_change_in_sales
FROM
    SalesPeriods
ORDER BY
    calendar_year