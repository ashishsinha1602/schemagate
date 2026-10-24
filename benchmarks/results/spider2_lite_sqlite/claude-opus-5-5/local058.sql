WITH seg AS (
  SELECT p.segment,
         COUNT(DISTINCT CASE WHEN s.fiscal_year = 2020 THEN s.product_code END) AS cnt_2020,
         COUNT(DISTINCT CASE WHEN s.fiscal_year = 2021 THEN s.product_code END) AS cnt_2021
  FROM hardware_fact_sales_monthly s
  JOIN hardware_dim_product p ON p.product_code = s.product_code
  WHERE s.fiscal_year IN (2020, 2021)
  GROUP BY p.segment
)
SELECT segment, cnt_2020 AS unique_products_2020
FROM seg
ORDER BY CASE WHEN cnt_2020 = 0 THEN NULL ELSE (cnt_2021 - cnt_2020) * 100.0 / cnt_2020 END DESC