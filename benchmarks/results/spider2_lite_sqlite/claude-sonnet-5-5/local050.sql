WITH m AS (
  SELECT s.prod_id, t.calendar_year AS y, t.calendar_month_number AS mo, SUM(s.amount_sold) AS amt
  FROM sales s
  JOIN customers c ON s.cust_id = c.cust_id
  JOIN countries co ON c.country_id = co.country_id
  JOIN times t ON s.time_id = t.time_id
  JOIN promotions p ON s.promo_id = p.promo_id
  JOIN channels ch ON s.channel_id = ch.channel_id
  WHERE co.country_name = 'France'
    AND p.promo_total_id = 1
    AND ch.channel_total_id = 1
    AND t.calendar_year IN (2019, 2020)
  GROUP BY s.prod_id, t.calendar_year, t.calendar_month_number
),
proj AS (
  SELECT a.prod_id, a.mo, ((b.amt - a.amt) / a.amt) * b.amt + b.amt AS p
  FROM m a
  JOIN m b ON a.prod_id = b.prod_id AND a.mo = b.mo AND a.y = 2019 AND b.y = 2020
),
monthly AS (
  SELECT proj.mo,
         ROUND(AVG(proj.p * COALESCE((SELECT cu.to_us FROM currency cu WHERE cu.country = 'France' AND cu.year = 2021 AND cu.month = proj.mo), 1)), 2) AS avg_usd
  FROM proj
  GROUP BY proj.mo
),
ranked AS (
  SELECT avg_usd, ROW_NUMBER() OVER (ORDER BY avg_usd) AS rn, COUNT(*) OVER () AS cnt
  FROM monthly
)
SELECT AVG(avg_usd) AS median_avg_monthly_projected_sales_usd
FROM ranked
WHERE rn IN ((cnt + 1) / 2, (cnt + 2) / 2)