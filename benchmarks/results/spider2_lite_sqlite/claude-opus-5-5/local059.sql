WITH product_totals AS (
  SELECT p.division, s.product_code, SUM(s.sold_quantity) AS total_qty
  FROM hardware_fact_sales_monthly s
  JOIN hardware_dim_product p ON p.product_code = s.product_code
  WHERE s.date >= '2021-01-01' AND s.date < '2022-01-01'
  GROUP BY p.division, s.product_code
),
ranked AS (
  SELECT division, product_code, total_qty,
         ROW_NUMBER() OVER (PARTITION BY division ORDER BY total_qty DESC) AS rn
  FROM product_totals
)
SELECT AVG(total_qty) AS avg_top3_quantity
FROM ranked
WHERE rn <= 3