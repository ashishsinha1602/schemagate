WITH customer_profits AS (
  SELECT
    c.cust_id,
    SUM(p.quantity_sold * (p.unit_price - p.unit_cost)) AS total_profit
  FROM profits AS p
  JOIN customers AS c
    ON p.cust_id = c.cust_id
  JOIN countries AS co
    ON c.country_id = co.country_id
  JOIN times AS t
    ON p.time_id = t.time_id
  WHERE
    co.country_name = 'Italy' AND t.calendar_month_name = 'December' AND t.calendar_year = 2021
  GROUP BY
    c.cust_id
), profit_stats AS (
  SELECT
    MIN(total_profit) AS min_overall_profit,
    MAX(total_profit) AS max_overall_profit,
    (MAX(total_profit) - MIN(total_profit)) AS overall_range
  FROM customer_profits
)
SELECT
  CASE
    WHEN ps.overall_range = 0
    THEN 1
    WHEN cp.total_profit = ps.max_overall_profit
    THEN 10
    ELSE CAST(
        (cp.total_profit - ps.min_overall_profit) * 10.0 / ps.overall_range
        AS INTEGER
    ) + 1
  END AS bucket_number,
  COUNT(cp.cust_id) AS number_of_customers,
  MIN(cp.total_profit) AS min_total_profit_in_bucket,
  MAX(cp.total_profit) AS max_total_profit_in_bucket
FROM customer_profits AS cp, profit_stats AS ps
GROUP BY
  bucket_number
ORDER BY
  bucket_number