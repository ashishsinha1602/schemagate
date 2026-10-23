WITH cust_profit AS (
  SELECT p.cust_id,
         SUM(p.amount_sold - p.unit_cost * p.quantity_sold) AS profit
  FROM profits p
  JOIN customers c ON c.cust_id = p.cust_id
  JOIN countries co ON co.country_id = c.country_id
  JOIN times t ON t.time_id = p.time_id
  WHERE co.country_name = 'Italy'
    AND t.calendar_month_desc = '2021-12'
  GROUP BY p.cust_id
),
tiers AS (
  SELECT cust_id, profit, NTILE(10) OVER (ORDER BY profit DESC) AS tier
  FROM cust_profit
)
SELECT tier,
       MAX(profit) AS highest_profit,
       MIN(profit) AS lowest_profit
FROM tiers
GROUP BY tier
ORDER BY tier