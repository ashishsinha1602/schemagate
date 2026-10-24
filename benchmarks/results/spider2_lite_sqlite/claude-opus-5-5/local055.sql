WITH artist_sales AS (
  SELECT ar.ArtistId, ar.Name, SUM(ii.UnitPrice * ii.Quantity) AS sales
  FROM invoice_items ii
  JOIN tracks t ON t.TrackId = ii.TrackId
  JOIN albums al ON al.AlbumId = t.AlbumId
  JOIN artists ar ON ar.ArtistId = al.ArtistId
  GROUP BY ar.ArtistId, ar.Name
),
top_artist AS (
  SELECT ArtistId FROM artist_sales ORDER BY sales DESC, Name ASC LIMIT 1
),
bottom_artist AS (
  SELECT ArtistId FROM artist_sales ORDER BY sales ASC, Name ASC LIMIT 1
),
cust_spend AS (
  SELECT i.CustomerId, al.ArtistId, SUM(ii.UnitPrice * ii.Quantity) AS spent
  FROM invoice_items ii
  JOIN invoices i ON i.InvoiceId = ii.InvoiceId
  JOIN tracks t ON t.TrackId = ii.TrackId
  JOIN albums al ON al.AlbumId = t.AlbumId
  WHERE al.ArtistId IN (SELECT ArtistId FROM top_artist UNION SELECT ArtistId FROM bottom_artist)
  GROUP BY i.CustomerId, al.ArtistId
)
SELECT ABS(
  (SELECT AVG(spent) FROM cust_spend WHERE ArtistId = (SELECT ArtistId FROM top_artist))
  - (SELECT AVG(spent) FROM cust_spend WHERE ArtistId = (SELECT ArtistId FROM bottom_artist))
) AS avg_spending_difference