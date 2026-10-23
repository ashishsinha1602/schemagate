WITH monthly_sales_indexed AS (
    SELECT
        product_id,
        mth,
        qty,
        CAST(SUBSTR(mth, 1, 4) AS INTEGER) AS yr,
        (CAST(SUBSTR(mth, 1, 4) AS INTEGER) - 2016) * 12 + CAST(SUBSTR(mth, 6, 2) AS INTEGER) AS month_index
    FROM main.monthly_sales
),
cma_calculation AS (
    SELECT
        product_id,
        mth,
        qty,
        yr,
        month_index,
        -- First window: 5 months before and 6 months after (12 months total including current)
        AVG(qty) OVER (PARTITION BY product_id ORDER BY month_index ROWS BETWEEN 5 PRECEDING AND 6 FOLLOWING) AS avg1,
        -- Second window: 6 months before and 5 months after (12 months total including current)
        AVG(qty) OVER (PARTITION BY product_id ORDER BY month_index ROWS BETWEEN 6 PRECEDING AND 5 FOLLOWING) AS avg2
    FROM monthly_sales_indexed
),
sales_ratio AS (
    SELECT
        product_id,
        mth,
        qty,
        yr,
        month_index,
        (avg1 + avg2) / 2.0 AS cma, -- Centered Moving Average
        qty / ((avg1 + avg2) / 2.0) AS ratio -- Sales-to-CMA Ratio
    FROM cma_calculation
    WHERE month_index BETWEEN 7 AND 30 -- Restriction to months between the 7th and 30th time steps
),
product_2017_ratios AS (
    SELECT
        product_id,
        mth,
        ratio
    FROM sales_ratio
    WHERE yr = 2017 -- Filter for the year 2017
)
SELECT
    p.name
FROM product_2017_ratios pr
JOIN main.products p ON pr.product_id = p.id
GROUP BY
    pr.product_id, p.name
HAVING
    COUNT(DISTINCT pr.mth) = 12 -- Ensure data for all 12 months of 2017
    AND MIN(pr.ratio) > 2