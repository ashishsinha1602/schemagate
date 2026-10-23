WITH cp AS (
  SELECT p.cust_id, SUM(p.quantity_sold * (p.unit_price - p.unit_cost)) AS total_profit
  FROM profits p
  JOIN customers c ON c.cust_id = p.cust_id
  JOIN countries co ON co.country_id = c.country_id
  JOIN times t ON t.time_id = p.time_id
  WHERE co.country_name = 'Italy' AND t.calendar_month_desc = '2021-12'
  GROUP BY p.cust_id
),
b AS (
  SELECT MIN(total_profit) AS mn, MAX(total_profit) AS mx FROM cp
)
SELECT bucket,
       COUNT(*) AS num_customers,
       MIN(total_profit) AS min_profit,
       MAX(total_profit) AS max_profit
FROM (
  SELECT cp.cust_id, cp.total_profit,
         CASE WHEN b.mx = b.mn THEN 0
              ELSE MIN(9, CAST((cp.total_profit - b.mn) * 10.0 / (b.mx - b.mn) AS INTEGER))
         END AS bucket
  FROM cp, b
)
GROUP BY bucket
ORDER BY bucket