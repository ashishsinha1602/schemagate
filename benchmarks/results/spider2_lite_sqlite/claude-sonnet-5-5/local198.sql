WITH cs AS (
  SELECT c.Country, SUM(i.Total) AS total
  FROM customers c
  JOIN invoices i ON i.CustomerId = c.CustomerId
  WHERE c.Country IN (
    SELECT Country FROM customers GROUP BY Country HAVING COUNT(*) > 4
  )
  GROUP BY c.Country
),
r AS (
  SELECT total,
         ROW_NUMBER() OVER (ORDER BY total) AS rn,
         COUNT(*) OVER () AS cnt
  FROM cs
)
SELECT AVG(total) AS median_total_sales
FROM r
WHERE rn IN ((cnt + 1) / 2, (cnt + 2) / 2)