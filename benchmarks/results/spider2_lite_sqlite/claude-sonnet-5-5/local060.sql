WITH base AS (
  SELECT cu.cust_city_id AS city_id, s.prod_id, t.calendar_quarter_desc AS q, s.amount_sold
  FROM sales s
  JOIN customers cu ON cu.cust_id = s.cust_id
  JOIN countries co ON co.country_id = cu.country_id
  JOIN times t ON t.time_id = s.time_id
  JOIN promotions p ON p.promo_id = s.promo_id
  WHERE (co.country_iso_code = 'US' OR co.country_name LIKE 'United States%')
    AND p.promo_category = 'NO PROMOTION'
    AND t.calendar_year IN (2019, 2020)
    AND t.calendar_quarter_number = 4
),
city_ok AS (
  SELECT city_id
  FROM base
  GROUP BY city_id
  HAVING SUM(CASE WHEN q LIKE '2019%' THEN amount_sold ELSE 0 END) > 0
     AND SUM(CASE WHEN q LIKE '2020%' THEN amount_sold ELSE 0 END) >= 1.2 * SUM(CASE WHEN q LIKE '2019%' THEN amount_sold ELSE 0 END)
),
fb AS (
  SELECT * FROM base WHERE city_id IN (SELECT city_id FROM city_ok)
),
prod_rank AS (
  SELECT prod_id,
         SUM(amount_sold) AS total_sales,
         SUM(CASE WHEN q LIKE '2019%' THEN amount_sold ELSE 0 END) AS s19,
         SUM(CASE WHEN q LIKE '2020%' THEN amount_sold ELSE 0 END) AS s20,
         NTILE(5) OVER (ORDER BY SUM(amount_sold) DESC) AS nt
  FROM fb
  GROUP BY prod_id
),
qtot AS (
  SELECT SUM(CASE WHEN q LIKE '2019%' THEN amount_sold ELSE 0 END) AS t19,
         SUM(CASE WHEN q LIKE '2020%' THEN amount_sold ELSE 0 END) AS t20
  FROM fb
)
SELECT pr.prod_id,
       p.prod_name,
       pr.s19 * 1.0 / qt.t19 AS share_q4_2019,
       pr.s20 * 1.0 / qt.t20 AS share_q4_2020,
       pr.s20 * 1.0 / qt.t20 - pr.s19 * 1.0 / qt.t19 AS share_change
FROM prod_rank pr
JOIN products p ON p.prod_id = pr.prod_id
CROSS JOIN qtot qt
WHERE pr.nt = 1
ORDER BY share_change DESC