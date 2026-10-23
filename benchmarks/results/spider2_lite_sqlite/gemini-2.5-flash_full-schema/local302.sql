WITH SalesPeriods AS (
    SELECT
        region,
        platform,
        age_band,
        demographic,
        customer_type,
        sales,
        CASE
            WHEN week_date >= '2020-03-23' AND week_date < '2020-06-15' THEN 'before'
            WHEN week_date >= '2020-06-15' AND week_date <= '2020-09-07' THEN 'after'
            ELSE NULL
        END AS period
    FROM main.cleaned_weekly_sales
    WHERE week_date >= '2020-03-23' AND week_date <= '2020-09-07'
),
AttributeSales AS (
    SELECT
        'region' AS attribute_type,
        region AS attribute_value,
        period,
        SUM(sales) AS total_sales
    FROM SalesPeriods
    WHERE region IS NOT NULL
    GROUP BY region, period

    UNION ALL

    SELECT
        'platform' AS attribute_type,
        platform AS attribute_value,
        period,
        SUM(sales) AS total_sales
    FROM SalesPeriods
    WHERE platform IS NOT NULL
    GROUP BY platform, period

    UNION ALL

    SELECT
        'age_band' AS attribute_type,
        age_band AS attribute_value,
        period,
        SUM(sales) AS total_sales
    FROM SalesPeriods
    WHERE age_band IS NOT NULL AND age_band != 'unknown'
    GROUP BY age_band, period

    UNION ALL

    SELECT
        'demographic' AS attribute_type,
        demographic AS attribute_value,
        period,
        SUM(sales) AS total_sales
    FROM SalesPeriods
    WHERE demographic IS NOT NULL AND demographic != 'unknown'
    GROUP BY demographic, period

    UNION ALL

    SELECT
        'customer_type' AS attribute_type,
        customer_type AS attribute_value,
        period,
        SUM(sales) AS total_sales
    FROM SalesPeriods
    WHERE customer_type IS NOT NULL
    GROUP BY customer_type, period
),
PercentageChanges AS (
    SELECT
        s_before.attribute_type,
        s_before.attribute_value,
        s_before.total_sales AS sales_before,
        s_after.total_sales AS sales_after,
        CASE
            WHEN s_before.total_sales = 0 THEN NULL
            ELSE ((s_after.total_sales - s_before.total_sales) * 100.0 / s_before.total_sales)
        END AS percentage_change
    FROM AttributeSales s_before
    JOIN AttributeSales s_after
        ON s_before.attribute_type = s_after.attribute_type
        AND s_before.attribute_value = s_after.attribute_value
    WHERE s_before.period = 'before'
      AND s_after.period = 'after'
),
AvgPercentageChangesByType AS (
    SELECT
        attribute_type,
        AVG(percentage_change) AS avg_pct_change
    FROM PercentageChanges
    WHERE percentage_change IS NOT NULL
    GROUP BY attribute_type
)
SELECT
    attribute_type,
    avg_pct_change
FROM AvgPercentageChangesByType
ORDER BY avg_pct_change ASC
LIMIT 1