WITH delivered_orders_2016_2018 AS (
  SELECT
    CAST(SUBSTR(order_purchase_timestamp, 1, 4) AS INTEGER) AS order_year,
    CAST(SUBSTR(order_purchase_timestamp, 6, 2) AS INTEGER) AS order_month,
    order_id
  FROM main.olist_orders
  WHERE
    order_status = 'delivered' AND CAST(SUBSTR(order_purchase_timestamp, 1, 4) AS INTEGER) IN (2016, 2017, 2018)
), annual_volumes AS (
  SELECT
    order_year,
    COUNT(order_id) AS annual_order_count
  FROM delivered_orders_2016_2018
  GROUP BY
    order_year
), lowest_annual_year AS (
  SELECT
    order_year
  FROM annual_volumes
  ORDER BY
    annual_order_count ASC
  LIMIT 1
), monthly_volumes_in_lowest_year AS (
  SELECT
    t1.order_year,
    t1.order_month,
    COUNT(t1.order_id) AS monthly_order_count
  FROM delivered_orders_2016_2018 AS t1
  INNER JOIN lowest_annual_year AS t2
    ON t1.order_year = t2.order_year
  GROUP BY
    t1.order_year,
    t1.order_month
)
SELECT
  MAX(monthly_order_count)
FROM monthly_volumes_in_lowest_year