WITH monthly_interest_data AS (
    SELECT
        im.month_year,
        CAST(SUBSTR(im.month_year, 4, 4) AS INTEGER) AS year_num,
        CAST(SUBSTR(im.month_year, 1, 2) AS INTEGER) AS month_num,
        im.interest_id,
        im.composition * 1.0 / im.index_value AS avg_composition_value
    FROM main.interest_metrics AS im
    WHERE
        (im._year = 2018 AND im._month >= 9) OR
        (im._year = 2019 AND im._month <= 8)
),
ranked_monthly_interests AS (
    SELECT
        mid.month_year,
        mid.year_num,
        mid.month_num,
        mid.interest_id,
        mid.avg_composition_value,
        ROW_NUMBER() OVER (PARTITION BY mid.month_year ORDER BY mid.avg_composition_value DESC) AS rnk
    FROM monthly_interest_data AS mid
),
top_monthly_interests AS (
    SELECT
        rmi.month_year,
        rmi.year_num,
        rmi.month_num,
        imi.interest_name,
        rmi.avg_composition_value AS max_index_composition
    FROM ranked_monthly_interests AS rmi
    JOIN main.interest_map AS imi
        ON rmi.interest_id = imi.id
    WHERE rmi.rnk = 1
)
SELECT
    tmi.month_year AS date,
    tmi.interest_name,
    tmi.max_index_composition,
    AVG(tmi.max_index_composition) OVER (ORDER BY tmi.year_num, tmi.month_num ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS rolling_avg_max_composition,
    LAG(tmi.interest_name, 1) OVER (ORDER BY tmi.year_num, tmi.month_num) AS prev_month_interest_name,
    LAG(tmi.max_index_composition, 1) OVER (ORDER BY tmi.year_num, tmi.month_num) AS prev_month_max_index_composition,
    LAG(tmi.interest_name, 2) OVER (ORDER BY tmi.year_num, tmi.month_num) AS two_months_ago_interest_name,
    LAG(tmi.max_index_composition, 2) OVER (ORDER BY tmi.year_num, tmi.month_num) AS two_months_ago_max_index_composition
FROM top_monthly_interests AS tmi
ORDER BY tmi.year_num, tmi.month_num