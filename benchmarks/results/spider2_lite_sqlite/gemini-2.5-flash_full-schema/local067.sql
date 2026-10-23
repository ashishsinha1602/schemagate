WITH CustomerProfits AS (
  SELECT
    p.cust_id,
    SUM(p.amount_sold - (p.quantity_sold * p.unit_cost)) AS total_profit
  FROM profits AS p
  JOIN times AS t
    ON p.time_id = t.time_id
  JOIN customers AS c
    ON p.cust_id = c.cust_id
  JOIN countries AS co
    ON c.country_id = co.country_id
  WHERE
    t.calendar_month_number = 12 AND t.calendar_year = 2021 AND co.country_name = 'Italy'
  GROUP BY
    p.cust_id
), CustomerTiers AS (
  SELECT
    total_profit,
    NTILE(10) OVER (ORDER BY total_profit) AS profit_tier
  FROM CustomerProfits
)
SELECT
  profit_tier,
  MAX(total_profit) AS highest_profit,
  MIN(total_profit) AS lowest_profit
FROM CustomerTiers
GROUP BY
  profit_tier
ORDER BY
  profit_tier