WITH t AS (
  SELECT p.division, p.product_code, SUM(s.sold_quantity) AS total_qty
  FROM hardware_fact_sales_monthly s
  JOIN hardware_dim_product p ON p.product_code = s.product_code
  WHERE substr(s.date,1,4) = '2021'
  GROUP BY p.division, p.product_code
),
r AS (
  SELECT division, product_code, total_qty,
         ROW_NUMBER() OVER (PARTITION BY division ORDER BY total_qty DESC) AS rn
  FROM t
)
SELECT AVG(total_qty) AS avg_quantity_sold
FROM r
WHERE rn <= 3