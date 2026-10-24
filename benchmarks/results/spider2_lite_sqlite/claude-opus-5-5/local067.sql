WITH cust_profit AS (
  SELECT p.cust_id,
         SUM(p.quantity_sold * (p.unit_price - p.unit_cost)) AS profit
  FROM profits p
  JOIN customers c ON c.cust_id = p.cust_id
  JOIN countries co ON co.country_id = c.country_id
  JOIN times t ON t.time_id = p.time_id
  WHERE co.country_name = 'Italy'
    AND t.calendar_year = 2021
    AND t.calendar_month_number = 12
  GROUP BY p.cust_id
),
tiered AS (
  SELECT cust_id, profit,
         NTILE(10) OVER (ORDER BY profit) AS tier
  FROM cust_profit
)
SELECT tier,
       MAX(profit) AS highest_profit,
       MIN(profit) AS lowest_profit
FROM tiered
GROUP BY tier
ORDER BY tier