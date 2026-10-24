WITH cust_profit AS (
  SELECT s.cust_id,
         SUM(s.quantity_sold * (c.unit_price - c.unit_cost)) AS total_profit
  FROM sales s
  JOIN costs c
    ON c.prod_id = s.prod_id
   AND c.time_id = s.time_id
   AND c.promo_id = s.promo_id
   AND c.channel_id = s.channel_id
  JOIN customers cu ON cu.cust_id = s.cust_id
  JOIN countries co ON co.country_id = cu.country_id
  JOIN times t ON t.time_id = s.time_id
  WHERE co.country_name = 'Italy'
    AND t.calendar_year = 2021
    AND t.calendar_month_number = 12
  GROUP BY s.cust_id
),
bounds AS (
  SELECT MIN(total_profit) AS min_p, MAX(total_profit) AS max_p
  FROM cust_profit
),
bucketed AS (
  SELECT cp.cust_id, cp.total_profit,
         CASE
           WHEN b.max_p = b.min_p THEN 1
           ELSE MIN(10, CAST((cp.total_profit - b.min_p) * 10.0 / (b.max_p - b.min_p) AS INTEGER) + 1)
         END AS bucket
  FROM cust_profit cp
  CROSS JOIN bounds b
)
SELECT bucket,
       COUNT(*) AS num_customers,
       MIN(total_profit) AS min_profit,
       MAX(total_profit) AS max_profit
FROM bucketed
GROUP BY bucket
ORDER BY bucket