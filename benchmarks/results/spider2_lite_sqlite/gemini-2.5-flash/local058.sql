WITH
  Products2020 AS (
    SELECT
      dp.segment,
      COUNT(DISTINCT fs.product_code) AS unique_products_2020
    FROM main.hardware_fact_sales_monthly AS fs
    JOIN main.hardware_dim_product AS dp
      ON fs.product_code = dp.product_code
    WHERE
      fs.fiscal_year = 2020
    GROUP BY
      dp.segment
  ),
  Products2021 AS (
    SELECT
      dp.segment,
      COUNT(DISTINCT fs.product_code) AS unique_products_2021
    FROM main.hardware_fact_sales_monthly AS fs
    JOIN main.hardware_dim_product AS dp
      ON fs.product_code = dp.product_code
    WHERE
      fs.fiscal_year = 2021
    GROUP BY
      dp.segment
  )
SELECT
  p2020.segment,
  p2020.unique_products_2020
FROM Products2020 AS p2020
LEFT JOIN Products2021 AS p2021
  ON p2020.segment = p2021.segment
ORDER BY
  CASE
    WHEN p2020.unique_products_2020 = 0
    THEN -1.0 -- Handle division by zero or no products in 2020, effectively putting them at the bottom
    ELSE (
      (
        COALESCE(p2021.unique_products_2021, 0) - p2020.unique_products_2020
      ) * 1.0 / p2020.unique_products_2020
    )
  END DESC