WITH agg AS (
  SELECT s.prod_id,
         t.calendar_month_number AS month,
         t.calendar_year AS year,
         SUM(s.amount_sold) AS amt
  FROM sales s
  JOIN customers cu ON s.cust_id = cu.cust_id
  JOIN countries co ON cu.country_id = co.country_id
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
  SELECT a.prod_id,
         a.month,
         ((b.amt - a.amt) / a.amt) * b.amt + b.amt AS proj_amt
  FROM agg a
  JOIN agg b
    ON a.prod_id = b.prod_id
   AND a.month = b.month
   AND a.year = 2019
   AND b.year = 2020
)
SELECT pr.month,
       ROUND(AVG(pr.proj_amt * COALESCE(cur.to_us, 1)), 2) AS avg_projected_sales_usd
FROM proj pr
LEFT JOIN currency cur
  ON cur.country = 'France'
 AND cur.year = 2021
 AND cur.month = pr.month
GROUP BY pr.month
ORDER BY pr.month