WITH base AS (
  SELECT s.prod_id, c.cust_city_id, t.calendar_year AS yr, s.amount_sold
  FROM sales s
  JOIN customers c ON c.cust_id = s.cust_id
  JOIN countries co ON co.country_id = c.country_id
  JOIN times t ON t.time_id = s.time_id
  JOIN promotions p ON p.promo_id = s.promo_id
  WHERE co.country_iso_code = 'US'
    AND p.promo_category = 'NO PROMOTION'
    AND t.calendar_quarter_number = 4
    AND t.calendar_year IN (2019, 2020)
),
city_sales AS (
  SELECT cust_city_id,
         SUM(CASE WHEN yr = 2019 THEN amount_sold ELSE 0 END) AS s2019,
         SUM(CASE WHEN yr = 2020 THEN amount_sold ELSE 0 END) AS s2020
  FROM base
  GROUP BY cust_city_id
),
good_cities AS (
  SELECT cust_city_id
  FROM city_sales
  WHERE s2019 > 0 AND s2020 >= 1.2 * s2019
),
filtered AS (
  SELECT b.*
  FROM base b
  JOIN good_cities g ON g.cust_city_id = b.cust_city_id
),
prod_sales AS (
  SELECT prod_id,
         SUM(amount_sold) AS total_sales,
         SUM(CASE WHEN yr = 2019 THEN amount_sold ELSE 0 END) AS p2019,
         SUM(CASE WHEN yr = 2020 THEN amount_sold ELSE 0 END) AS p2020
  FROM filtered
  GROUP BY prod_id
),
ranked AS (
  SELECT ps.*, NTILE(5) OVER (ORDER BY total_sales DESC) AS tile
  FROM prod_sales ps
),
year_totals AS (
  SELECT SUM(CASE WHEN yr = 2019 THEN amount_sold ELSE 0 END) AS t2019,
         SUM(CASE WHEN yr = 2020 THEN amount_sold ELSE 0 END) AS t2020
  FROM filtered
)
SELECT r.prod_id,
       pr.prod_name,
       r.p2019 * 1.0 / yt.t2019 AS share_q4_2019,
       r.p2020 * 1.0 / yt.t2020 AS share_q4_2020,
       r.p2020 * 1.0 / yt.t2020 - r.p2019 * 1.0 / yt.t2019 AS share_change
FROM ranked r
JOIN products pr ON pr.prod_id = r.prod_id
CROSS JOIN year_totals yt
WHERE r.tile = 1
ORDER BY share_change DESC