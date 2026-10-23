WITH monthly_sales_with_month_num AS (
    SELECT
        product_id,
        mth,
        qty,
        (CAST(SUBSTR(mth, 1, 4) AS INTEGER) - 2016) * 12 + CAST(SUBSTR(mth, 6, 2) AS INTEGER) AS mth_num
    FROM main.monthly_sales
),
sales_with_cma_components AS (
    SELECT
        product_id,
        mth,
        qty,
        mth_num,
        -- Sum of sales for 13 months (from 6 months before to 6 months after the current month)
        SUM(qty) OVER (PARTITION BY product_id ORDER BY mth_num ROWS BETWEEN 6 PRECEDING AND 6 FOLLOWING) AS sum_13_months,
        -- Sum of sales for 11 months (from 5 months before to 5 months after the current month)
        SUM(qty) OVER (PARTITION BY product_id ORDER BY mth_num ROWS BETWEEN 5 PRECEDING AND 5 FOLLOWING) AS sum_11_months
    FROM monthly_sales_with_month_num
    -- Apply the restriction: only consider target months between the 7th and 30th time steps
    WHERE mth_num >= 7 AND mth_num <= 30
),
sales_with_ratio AS (
    SELECT
        product_id,
        mth,
        qty,
        mth_num,
        -- Calculate the Centered Moving Average (CMA)
        -- CMA = ( (Sum(S_i from t-5 to t+6)/12) + (Sum(S_i from t-6 to t+5)/12) ) / 2
        -- This simplifies to (sum_13_months + sum_11_months) / 24.0
        (sum_13_months + sum_11_months) / 24.0 AS cma,
        -- Calculate the Sales-to-CMA Ratio
        qty / ((sum_13_months + sum_11_months) / 24.0) AS ratio
    FROM sales_with_cma_components
    -- Filter for the year 2017 (mth_num 13 for Jan 2017 to 24 for Dec 2017)
    WHERE mth_num >= 13 AND mth_num <= 24
)
SELECT
    p.name
FROM sales_with_ratio AS s
JOIN main.products AS p
    ON s.product_id = p.id
GROUP BY
    p.id, p.name
HAVING
    MIN(s.ratio) > 2