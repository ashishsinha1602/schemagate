WITH sales AS (
  SELECT al.ArtistId, ar.Name, SUM(ii.UnitPrice * ii.Quantity) AS total
  FROM invoice_items ii
  JOIN tracks t ON t.TrackId = ii.TrackId
  JOIN albums al ON al.AlbumId = t.AlbumId
  JOIN artists ar ON ar.ArtistId = al.ArtistId
  GROUP BY al.ArtistId, ar.Name
),
top_a AS (
  SELECT ArtistId FROM sales ORDER BY total DESC, Name ASC LIMIT 1
),
bot_a AS (
  SELECT ArtistId FROM sales ORDER BY total ASC, Name ASC LIMIT 1
),
cust AS (
  SELECT al.ArtistId, i.CustomerId, SUM(ii.UnitPrice * ii.Quantity) AS spent
  FROM invoice_items ii
  JOIN invoices i ON i.InvoiceId = ii.InvoiceId
  JOIN tracks t ON t.TrackId = ii.TrackId
  JOIN albums al ON al.AlbumId = t.AlbumId
  WHERE al.ArtistId IN (SELECT ArtistId FROM top_a UNION SELECT ArtistId FROM bot_a)
  GROUP BY al.ArtistId, i.CustomerId
)
SELECT ABS(
  (SELECT AVG(spent) FROM cust WHERE ArtistId = (SELECT ArtistId FROM top_a))
  - (SELECT AVG(spent) FROM cust WHERE ArtistId = (SELECT ArtistId FROM bot_a))
) AS avg_spend_difference