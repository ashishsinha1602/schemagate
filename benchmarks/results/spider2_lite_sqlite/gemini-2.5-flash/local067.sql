WITH customer_dec_2021_profits AS (
  SELECT
    p.cust_id,
    SUM(p.amount_sold - (p.unit_cost * p.quantity_sold)) AS total_customer_profit
  FROM main.profits AS p
  JOIN main.customers AS c
    ON p.cust_id = c.cust_id
  JOIN main.countries AS co
    ON c.country_id = co.country_id
  JOIN main.times AS t
    ON p.time_id = t.time_id
  WHERE
    co.country_name = 'Italy' AND t.calendar_month_number = 12 AND t.calendar_year = 2021
  GROUP BY
    p.cust_id
), tiered_customers AS (
  SELECT
    cust_id,
    total_customer_profit,
    NTILE(10) OVER (ORDER BY total_customer_profit ASC) AS profit_tier
  FROM customer_dec_2021_profits
)
SELECT
  profit_tier,
  MIN(total_customer_profit) AS lowest_profit,
  MAX(total_customer_profit) AS highest_profit
FROM tiered_customers
GROUP BY
  profit_tier
ORDER BY
  profit_tier