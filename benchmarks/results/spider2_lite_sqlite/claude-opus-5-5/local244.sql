WITH stats AS (
  SELECT MIN(Milliseconds) / 60000.0 AS mn,
         AVG(Milliseconds) / 60000.0 AS av,
         MAX(Milliseconds) / 60000.0 AS mx
  FROM Track
),
rev AS (
  SELECT TrackId, SUM(UnitPrice * Quantity) AS revenue
  FROM InvoiceLine
  GROUP BY TrackId
),
cls AS (
  SELECT t.TrackId,
         t.Milliseconds / 60000.0 AS duration_min,
         CASE
           WHEN t.Milliseconds / 60000.0 <= (s.mn + s.av) / 2.0 THEN 'Short'
           WHEN t.Milliseconds / 60000.0 <= (s.av + s.mx) / 2.0 THEN 'Medium'
           ELSE 'Long'
         END AS category,
         COALESCE(r.revenue, 0) AS revenue
  FROM Track t
  CROSS JOIN stats s
  LEFT JOIN rev r ON r.TrackId = t.TrackId
)
SELECT category,
       MIN(duration_min) AS min_duration_minutes,
       MAX(duration_min) AS max_duration_minutes,
       SUM(revenue) AS total_revenue
FROM cls
GROUP BY category