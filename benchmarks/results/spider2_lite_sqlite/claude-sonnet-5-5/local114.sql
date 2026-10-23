WITH rep_sales AS (
  SELECT r.id AS region_id, r.name AS region_name, sr.id AS rep_id, sr.name AS rep_name,
         SUM(o.total_amt_usd) AS rep_total
  FROM web_region r
  JOIN web_sales_reps sr ON sr.region_id = r.id
  JOIN web_accounts a ON a.sales_rep_id = sr.id
  JOIN web_orders o ON o.account_id = a.id
  GROUP BY r.id, r.name, sr.id, sr.name
),
region_tot AS (
  SELECT r.id AS region_id, COUNT(o.id) AS num_orders, SUM(o.total_amt_usd) AS total_sales
  FROM web_region r
  JOIN web_sales_reps sr ON sr.region_id = r.id
  JOIN web_accounts a ON a.sales_rep_id = sr.id
  JOIN web_orders o ON o.account_id = a.id
  GROUP BY r.id
),
ranked AS (
  SELECT rs.*, MAX(rep_total) OVER (PARTITION BY region_id) AS max_total
  FROM rep_sales rs
)
SELECT rk.region_name, rt.num_orders, rt.total_sales, rk.rep_name AS top_rep_name, rk.rep_total AS top_rep_sales
FROM ranked rk
JOIN region_tot rt ON rt.region_id = rk.region_id
WHERE rk.rep_total = rk.max_total
ORDER BY rk.region_name, rk.rep_name