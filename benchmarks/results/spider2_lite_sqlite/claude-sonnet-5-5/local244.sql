WITH stats AS (
  SELECT MIN(Milliseconds) AS mn, AVG(Milliseconds) AS av, MAX(Milliseconds) AS mx
  FROM Track
),
classified AS (
  SELECT t.TrackId,
         t.Milliseconds,
         CASE
           WHEN t.Milliseconds <= (s.mn + s.av) / 2.0 THEN 'short'
           WHEN t.Milliseconds <= (s.av + s.mx) / 2.0 THEN 'medium'
           ELSE 'long'
         END AS category
  FROM Track t
  CROSS JOIN stats s
),
rev AS (
  SELECT TrackId, SUM(UnitPrice * Quantity) AS revenue
  FROM InvoiceLine
  GROUP BY TrackId
)
SELECT c.category,
       MIN(c.Milliseconds) / 60000.0 AS min_minutes,
       MAX(c.Milliseconds) / 60000.0 AS max_minutes,
       COALESCE(SUM(r.revenue), 0) AS total_revenue
FROM classified c
LEFT JOIN rev r ON r.TrackId = c.TrackId
GROUP BY c.category