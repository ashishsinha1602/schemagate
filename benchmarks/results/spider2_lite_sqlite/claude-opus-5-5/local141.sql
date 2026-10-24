WITH sales AS (
  SELECT salespersonid AS businessentityid,
         strftime('%Y', orderdate) AS yr,
         SUM(totaldue) AS total_sales
  FROM salesorderheader
  WHERE salespersonid IS NOT NULL
  GROUP BY salespersonid, strftime('%Y', orderdate)
),
quota AS (
  SELECT BusinessEntityID AS businessentityid,
         strftime('%Y', QuotaDate) AS yr,
         SUM(SalesQuota) AS annual_quota
  FROM SalesPersonQuotaHistory
  GROUP BY BusinessEntityID, strftime('%Y', QuotaDate)
)
SELECT s.businessentityid AS salesperson_id,
       s.yr AS year,
       s.total_sales,
       q.annual_quota,
       s.total_sales - q.annual_quota AS difference
FROM sales s
JOIN quota q
  ON q.businessentityid = s.businessentityid
 AND q.yr = s.yr
ORDER BY s.businessentityid, s.yr