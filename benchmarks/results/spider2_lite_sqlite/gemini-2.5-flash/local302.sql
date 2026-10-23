WITH sales_periods AS (
    SELECT
        region,
        platform,
        age_band,
        demographic,
        customer_type,
        sales,
        CASE
            WHEN week_date_formatted BETWEEN '2020-03-23' AND '2020-06-08' THEN 'before'
            WHEN week_date_formatted BETWEEN '2020-06-15' AND '2020-08-31' THEN 'after'
            ELSE NULL
        END AS period
    FROM
        main.cleaned_weekly_sales
    WHERE
        period IS NOT NULL
),
attribute_sales AS (
    SELECT
        'region' AS attribute_type,
        region AS attribute_value,
        SUM(CASE WHEN period = 'before' THEN sales ELSE 0 END) AS sales_before,
        SUM(CASE WHEN period = 'after' THEN sales ELSE 0 END) AS sales_after
    FROM
        sales_periods
    GROUP BY
        region

    UNION ALL

    SELECT
        'platform' AS attribute_type,
        platform AS attribute_value,
        SUM(CASE WHEN period = 'before' THEN sales ELSE 0 END) AS sales_before,
        SUM(CASE WHEN period = 'after' THEN sales ELSE 0 END) AS sales_after
    FROM
        sales_periods
    GROUP BY
        platform

    UNION ALL

    SELECT
        'age_band' AS attribute_type,
        age_band AS attribute_value,
        SUM(CASE WHEN period = 'before' THEN sales ELSE 0 END) AS sales_before,
        SUM(CASE WHEN period = 'after' THEN sales ELSE 0 END) AS sales_after
    FROM
        sales_periods
    GROUP BY
        age_band

    UNION ALL

    SELECT
        'demographic' AS attribute_type,
        demographic AS attribute_value,
        SUM(CASE WHEN period = 'before' THEN sales ELSE 0 END) AS sales_before,
        SUM(CASE WHEN period = 'after' THEN sales ELSE 0 END) AS sales_after
    FROM
        sales_periods
    GROUP BY
        demographic

    UNION ALL

    SELECT
        'customer_type' AS attribute_type,
        customer_type AS attribute_value,
        SUM(CASE WHEN period = 'before' THEN sales ELSE 0 END) AS sales_before,
        SUM(CASE WHEN period = 'after' THEN sales ELSE 0 END) AS sales_after
    FROM
        sales_periods
    GROUP BY
        customer_type
),
percentage_changes AS (
    SELECT
        attribute_type,
        attribute_value,
        CASE
            WHEN sales_before = 0 AND sales_after = 0 THEN 0.0
            WHEN sales_before = 0 THEN NULL -- Exclude infinite increase from average calculation
            ELSE ((CAST(sales_after AS REAL) - sales_before) / sales_before) * 100
        END AS percent_change
    FROM
        attribute_sales
),
avg_percentage_changes AS (
    SELECT
        attribute_type,
        AVG(percent_change) AS avg_percent_change
    FROM
        percentage_changes
    WHERE
        percent_change IS NOT NULL
    GROUP BY
        attribute_type
)
SELECT
    attribute_type,
    avg_percent_change
FROM
    avg_percentage_changes
ORDER BY
    avg_percent_change ASC