WITH order_details AS (
  SELECT r.id AS region_id, r.name AS region_name, s.id AS rep_id, s.name AS rep_name,
         o.id AS order_id, o.total_amt_usd
  FROM web_orders o
  JOIN web_accounts a ON o.account_id = a.id
  JOIN web_sales_reps s ON a.sales_rep_id = s.id
  JOIN web_region r ON s.region_id = r.id
),
region_totals AS (
  SELECT region_id, region_name, COUNT(order_id) AS num_orders, SUM(total_amt_usd) AS total_sales
  FROM order_details
  GROUP BY region_id, region_name
),
rep_totals AS (
  SELECT region_id, rep_id, rep_name, SUM(total_amt_usd) AS rep_sales
  FROM order_details
  GROUP BY region_id, rep_id, rep_name
),
ranked AS (
  SELECT region_id, rep_name, rep_sales,
         RANK() OVER (PARTITION BY region_id ORDER BY rep_sales DESC) AS rnk
  FROM rep_totals
)
SELECT rt.region_name, rt.num_orders, rt.total_sales, rk.rep_name, rk.rep_sales
FROM region_totals rt
JOIN ranked rk ON rk.region_id = rt.region_id AND rk.rnk = 1
ORDER BY rt.region_name, rk.rep_name