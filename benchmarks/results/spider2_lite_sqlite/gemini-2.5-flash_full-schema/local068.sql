WITH monthly_counts AS (
    SELECT
        CAST(strftime('%Y', insert_date) AS INTEGER) AS year,
        strftime('%m', insert_date) AS month,
        COUNT(city_id) AS total_cities_added_month
    FROM
        main.cities
    WHERE
        strftime('%m', insert_date) IN ('04', '05', '06')
        AND strftime('%Y', insert_date) IN ('2021', '2022', '2023')
    GROUP BY
        1, 2
),
with_running_total AS (
    SELECT
        year,
        month,
        total_cities_added_month,
        SUM(total_cities_added_month) OVER (PARTITION BY month ORDER BY year) AS cumulative_running_total_month
    FROM
        monthly_counts
),
with_lagged_values AS (
    SELECT
        year,
        month,
        total_cities_added_month,
        cumulative_running_total_month,
        LAG(total_cities_added_month, 1) OVER (PARTITION BY month ORDER BY year) AS prev_year_month_total,
        LAG(cumulative_running_total_month, 1) OVER (PARTITION BY month ORDER BY year) AS prev_year_running_total
    FROM
        with_running_total
)
SELECT
    year,
    CASE month
        WHEN '04' THEN 'April'
        WHEN '05' THEN 'May'
        WHEN '06' THEN 'June'
    END AS month,
    total_cities_added_month,
    cumulative_running_total_month,
    ROUND((total_cities_added_month - prev_year_month_total) * 100.0 / prev_year_month_total, 2) AS yoy_growth_monthly_total,
    ROUND((cumulative_running_total_month - prev_year_running_total) * 100.0 / prev_year_running_total, 2) AS yoy_growth_running_total
FROM
    with_lagged_values
WHERE
    year IN (2022, 2023)
ORDER BY
    year,
    month