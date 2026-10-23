WITH RECURSIVE toy_products AS (
    SELECT
        p.product_id
    FROM
        main.products AS p
    JOIN
        main.product_category_name_translation AS t
        ON p.product_category_name = t.product_category_name
    WHERE
        t.product_category_name_english = 'toys'
),
daily_toy_sales_raw AS (
    SELECT
        SUBSTR(o.order_purchase_timestamp, 1, 10) AS sale_date,
        SUM(oi.price) AS daily_sales_y
    FROM
        main.order_items AS oi
    JOIN
        main.orders AS o
        ON oi.order_id = o.order_id
    JOIN
        toy_products AS tp
        ON oi.product_id = tp.product_id
    WHERE
        SUBSTR(o.order_purchase_timestamp, 1, 10) >= '2017-01-01'
        AND SUBSTR(o.order_purchase_timestamp, 1, 10) <= '2018-08-29'
    GROUP BY
        sale_date
),
daily_sales_with_x AS (
    SELECT
        julianday(sale_date) - julianday('2017-01-01') AS x,
        daily_sales_y AS y
    FROM
        daily_toy_sales_raw
),
regression_stats AS (
    SELECT
        COUNT(x) AS N,
        SUM(x) AS sum_x,
        SUM(y) AS sum_y,
        SUM(x * y) AS sum_xy,
        SUM(x * x) AS sum_x2
    FROM
        daily_sales_with_x
),
regression_coeffs AS (
    SELECT
        (N * sum_xy - sum_x * sum_y) * 1.0 / (N * sum_x2 - sum_x * sum_x) AS m,
        (sum_y - (N * sum_xy - sum_x * sum_y) * 1.0 / (N * sum_x2 - sum_x * sum_x) * sum_x) * 1.0 / N AS b
    FROM
        regression_stats
),
date_series(dt) AS (
    SELECT '2018-12-03' -- Start 2 days before Dec 5 for symmetric MA
    UNION ALL
    SELECT DATE(dt, '+1 day')
    FROM date_series
    WHERE dt < '2018-12-10' -- End 2 days after Dec 8 for symmetric MA
),
predicted_sales AS (
    SELECT
        ds.dt AS prediction_date,
        (rc.m * (julianday(ds.dt) - julianday('2017-01-01')) + rc.b) AS predicted_y
    FROM
        date_series AS ds,
        regression_coeffs AS rc
),
moving_averages AS (
    SELECT
        prediction_date,
        AVG(predicted_y) OVER (ORDER BY prediction_date ROWS BETWEEN 2 PRECEDING AND 2 FOLLOWING) AS sma_5_day
    FROM
        predicted_sales
)
SELECT
    SUM(sma_5_day)
FROM
    moving_averages
WHERE
    prediction_date BETWEEN '2018-12-05' AND '2018-12-08'