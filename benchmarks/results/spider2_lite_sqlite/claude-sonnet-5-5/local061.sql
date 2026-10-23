WITH agg AS (
  SELECT s.prod_id, t.calendar_month_number AS m, t.calendar_year AS y, SUM(s.amount_sold) AS amt
  FROM sales s
  JOIN customers c ON s.cust_id = c.cust_id
  JOIN countries co ON c.country_id = co.country_id
  JOIN promotions p ON s.promo_id = p.promo_id
  JOIN channels ch ON s.channel_id = ch.channel_id
  JOIN times t ON s.time_id = t.time_id
  WHERE co.country_name = 'France'
    AND p.promo_total_id = 1
    AND ch.channel_total_id = 1
    AND t.calendar_year IN (2019, 2020)
  GROUP BY s.prod_id, t.calendar_month_number, t.calendar_year
),
proj AS (
  SELECT a19.prod_id, a19.m,
         ((a20.amt - a19.amt) / a19.amt) * a20.amt + a20.amt AS p
  FROM agg a19
  JOIN agg a20 ON a19.prod_id = a20.prod_id AND a19.m = a20.m
  WHERE a19.y = 2019 AND a20.y = 2020
)
SELECT proj.m AS month,
       ROUND(AVG(proj.p * COALESCE(cur.to_us, 1)), 2) AS avg_projected_usd
FROM proj
LEFT JOIN currency cur ON cur.country = 'France' AND cur.year = 2021 AND cur.month = proj.m
GROUP BY proj.m
ORDER BY proj.m