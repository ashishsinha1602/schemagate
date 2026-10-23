WITH sales_2021 AS (
  SELECT
    hfs.product_code,
    hdp.division,
    hfs.sold_quantity
  FROM main.hardware_fact_sales_monthly AS hfs
  JOIN main.hardware_dim_product AS hdp
    ON hfs.product_code = hdp.product_code
  WHERE
    STRFTIME('%Y', hfs.date) = '2021'
), product_division_sales AS (
  SELECT
    product_code,
    division,
    SUM(sold_quantity) AS total_sold_quantity
  FROM sales_2021
  GROUP BY
    product_code,
    division
), ranked_products AS (
  SELECT
    product_code,
    division,
    total_sold_quantity,
    RANK() OVER (PARTITION BY division ORDER BY total_sold_quantity DESC) AS rnk
  FROM product_division_sales
), top_3_products AS (
  SELECT
    total_sold_quantity
  FROM ranked_products
  WHERE
    rnk <= 3
)
SELECT
  AVG(total_sold_quantity)
FROM top_3_products