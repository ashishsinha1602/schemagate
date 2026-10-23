WITH base AS (
  SELECT s.prod_id, c.cust_city, t.calendar_quarter_id AS q, s.amount_sold
  FROM sales s
  JOIN customers c ON s.cust_id = c.cust_id
  JOIN countries co ON c.country_id = co.country_id
  JOIN times t ON s.time_id = t.time_id
  WHERE co.country_iso_code = 'US'
    AND s.promo_id = 999
    AND t.calendar_quarter_id IN (1772, 1776)
),
city_sales AS (
  SELECT cust_city,
         SUM(CASE WHEN q = 1772 THEN amount_sold ELSE 0 END) AS s19,
         SUM(CASE WHEN q = 1776 THEN amount_sold ELSE 0 END) AS s20
  FROM base
  GROUP BY cust_city
),
good_cities AS (
  SELECT cust_city FROM city_sales WHERE s19 > 0 AND s20 >= 1.2 * s19
),
fb AS (
  SELECT * FROM base WHERE cust_city IN (SELECT cust_city FROM good_cities)
),
prod_sales AS (
  SELECT prod_id,
         SUM(amount_sold) AS total,
         SUM(CASE WHEN q = 1772 THEN amount_sold ELSE 0 END) AS p19,
         SUM(CASE WHEN q = 1776 THEN amount_sold ELSE 0 END) AS p20
  FROM fb
  GROUP BY prod_id
),
ranked AS (
  SELECT prod_id, total, p19, p20,
         NTILE(5) OVER (ORDER BY total DESC) AS nt,
         p19 * 1.0 / SUM(p19) OVER () AS sh19,
         p20 * 1.0 / SUM(p20) OVER () AS sh20
  FROM prod_sales
)
SELECT r.prod_id, pr.prod_name, ABS(r.sh20 - r.sh19) * 100 AS share_change_pct_points
FROM ranked r
JOIN products pr ON r.prod_id = pr.prod_id
WHERE r.nt = 1
ORDER BY ABS(r.sh20 - r.sh19) ASC
LIMIT 1