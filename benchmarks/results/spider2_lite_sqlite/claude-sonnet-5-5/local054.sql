WITH top_artist AS (
  SELECT al.ArtistId
  FROM invoice_items ii
  JOIN tracks t ON t.TrackId = ii.TrackId
  JOIN albums al ON al.AlbumId = t.AlbumId
  GROUP BY al.ArtistId
  ORDER BY SUM(ii.UnitPrice * ii.Quantity) DESC
  LIMIT 1
)
SELECT c.FirstName, SUM(ii.UnitPrice * ii.Quantity) AS AmountSpent
FROM customers c
JOIN invoices i ON i.CustomerId = c.CustomerId
JOIN invoice_items ii ON ii.InvoiceId = i.InvoiceId
JOIN tracks t ON t.TrackId = ii.TrackId
JOIN albums al ON al.AlbumId = t.AlbumId
WHERE al.ArtistId = (SELECT ArtistId FROM top_artist)
GROUP BY c.CustomerId, c.FirstName
HAVING SUM(ii.UnitPrice * ii.Quantity) < 1