WITH base AS (
  SELECT s.prod_id,
         t.calendar_year AS yr,
         t.calendar_month_number AS mon,
         SUM(s.amount_sold) AS amt
  FROM sales s
  JOIN customers cu ON cu.cust_id = s.cust_id
  JOIN countries co ON co.country_id = cu.country_id
  JOIN times t ON t.time_id = s.time_id
  JOIN promotions p ON p.promo_id = s.promo_id
  JOIN channels ch ON ch.channel_id = s.channel_id
  WHERE co.country_name = 'France'
    AND p.promo_total_id = 1
    AND ch.channel_total_id = 1
    AND t.calendar_year IN (2019, 2020)
  GROUP BY s.prod_id, t.calendar_year, t.calendar_month_number
),
proj AS (
  SELECT a.prod_id,
         a.mon,
         (((b.amt - a.amt) / a.amt) * b.amt) + b.amt AS proj_amt
  FROM base a
  JOIN base b ON b.prod_id = a.prod_id AND b.mon = a.mon AND b.yr = 2020
  WHERE a.yr = 2019 AND a.amt <> 0
),
usd AS (
  SELECT pr.mon,
         pr.proj_amt * COALESCE(c.to_us, 1) AS proj_usd
  FROM proj pr
  LEFT JOIN currency c ON c.country = 'France' AND c.year = 2021 AND c.month = pr.mon
),
monthly AS (
  SELECT mon, ROUND(AVG(proj_usd), 2) AS avg_usd
  FROM usd
  GROUP BY mon
),
ordered AS (
  SELECT avg_usd,
         ROW_NUMBER() OVER (ORDER BY avg_usd) AS rn,
         COUNT(*) OVER () AS cnt
  FROM monthly
)
SELECT AVG(avg_usd) AS median_monthly_projected_sales_usd
FROM ordered
WHERE rn IN ((cnt + 1) / 2, (cnt + 2) / 2)