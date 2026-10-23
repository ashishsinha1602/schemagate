WITH sales_2021 AS (
  SELECT
    s.product_code,
    s.sold_quantity,
    p.division
  FROM main.hardware_fact_sales_monthly AS s
  JOIN main.hardware_dim_product AS p
    ON s.product_code = p.product_code
  WHERE
    s.date BETWEEN '2021-01-01' AND '2021-12-31'
), product_total_sales_by_division AS (
  SELECT
    division,
    product_code,
    SUM(sold_quantity) AS total_quantity_sold_per_product
  FROM sales_2021
  GROUP BY
    division,
    product_code
), ranked_products AS (
  SELECT
    division,
    product_code,
    ROW_NUMBER() OVER (PARTITION BY division ORDER BY total_quantity_sold_per_product DESC) AS rn
  FROM product_total_sales_by_division
), top_3_products_per_division AS (
  SELECT
    division,
    product_code
  FROM ranked_products
  WHERE
    rn <= 3
)
SELECT
  AVG(s.sold_quantity)
FROM sales_2021 AS s
JOIN top_3_products_per_division AS t3
  ON s.division = t3.division AND s.product_code = t3.product_code