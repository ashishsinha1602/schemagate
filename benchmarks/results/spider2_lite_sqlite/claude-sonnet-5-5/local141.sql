WITH sales AS (
  SELECT salespersonid AS pid, strftime('%Y', orderdate) AS yr, SUM(subtotal) AS total_sales
  FROM salesorderheader
  WHERE salespersonid IS NOT NULL
  GROUP BY salespersonid, strftime('%Y', orderdate)
),
quota AS (
  SELECT BusinessEntityID AS pid, strftime('%Y', QuotaDate) AS yr, SUM(SalesQuota) AS total_quota
  FROM SalesPersonQuotaHistory
  GROUP BY BusinessEntityID, strftime('%Y', QuotaDate)
),
keys AS (
  SELECT pid, yr FROM sales
  UNION
  SELECT pid, yr FROM quota
)
SELECT k.pid AS salesperson_id,
       k.yr AS year,
       COALESCE(s.total_sales, 0) AS total_sales,
       COALESCE(q.total_quota, 0) AS total_quota,
       COALESCE(s.total_sales, 0) - COALESCE(q.total_quota, 0) AS difference
FROM keys k
LEFT JOIN sales s ON s.pid = k.pid AND s.yr = k.yr
LEFT JOIN quota q ON q.pid = k.pid AND q.yr = k.yr
ORDER BY k.pid, k.yr