WITH c AS (
  SELECT p.segment,
         COUNT(DISTINCT CASE WHEN s.fiscal_year = 2020 THEN s.product_code END) AS product_count_2020,
         COUNT(DISTINCT CASE WHEN s.fiscal_year = 2021 THEN s.product_code END) AS product_count_2021
  FROM hardware_fact_sales_monthly s
  JOIN hardware_dim_product p ON p.product_code = s.product_code
  GROUP BY p.segment
)
SELECT segment, product_count_2020
FROM c
ORDER BY (product_count_2021 - product_count_2020) * 100.0 / NULLIF(product_count_2020, 0) DESC