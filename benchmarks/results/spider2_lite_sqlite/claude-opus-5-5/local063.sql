WITH base AS (
  SELECT s.prod_id, c.cust_city, c.cust_state_province, t.calendar_quarter_id AS qid, s.amount_sold
  FROM sales s
  JOIN customers c ON c.cust_id = s.cust_id
  JOIN countries co ON co.country_id = c.country_id
  JOIN times t ON t.time_id = s.time_id
  WHERE s.promo_id = 999
    AND co.country_iso_code = 'US'
    AND t.calendar_quarter_id IN (1772, 1776)
),
city_sales AS (
  SELECT cust_city, cust_state_province,
         SUM(CASE WHEN qid = 1772 THEN amount_sold ELSE 0 END) AS q1,
         SUM(CASE WHEN qid = 1776 THEN amount_sold ELSE 0 END) AS q2
  FROM base
  GROUP BY cust_city, cust_state_province
),
good_cities AS (
  SELECT cust_city, cust_state_province
  FROM city_sales
  WHERE q1 > 0 AND q2 >= 1.2 * q1
),
fb AS (
  SELECT b.*
  FROM base b
  JOIN good_cities g ON g.cust_city = b.cust_city AND g.cust_state_province = b.cust_state_province
),
prod_sales AS (
  SELECT prod_id,
         SUM(CASE WHEN qid = 1772 THEN amount_sold ELSE 0 END) AS p1,
         SUM(CASE WHEN qid = 1776 THEN amount_sold ELSE 0 END) AS p2,
         SUM(amount_sold) AS ptot
  FROM fb
  GROUP BY prod_id
),
ranked AS (
  SELECT ps.*,
         NTILE(5) OVER (ORDER BY ptot DESC) AS tile,
         p1 * 100.0 / SUM(p1) OVER () AS share1,
         p2 * 100.0 / SUM(p2) OVER () AS share2
  FROM prod_sales ps
)
SELECT r.prod_id, p.prod_name, r.share1, r.share2, r.share2 - r.share1 AS share_change
FROM ranked r
JOIN products p ON p.prod_id = r.prod_id
WHERE r.tile = 1
ORDER BY ABS(r.share2 - r.share1) ASC
LIMIT 1