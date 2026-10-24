WITH artist_sales AS (
  SELECT al.ArtistId, SUM(ii.UnitPrice * ii.Quantity) AS total_sales
  FROM invoice_items ii
  JOIN tracks t ON t.TrackId = ii.TrackId
  JOIN albums al ON al.AlbumId = t.AlbumId
  GROUP BY al.ArtistId
  ORDER BY total_sales DESC
  LIMIT 1
),
customer_spend AS (
  SELECT c.CustomerId, c.FirstName, SUM(ii.UnitPrice * ii.Quantity) AS amount_spent
  FROM invoice_items ii
  JOIN invoices i ON i.InvoiceId = ii.InvoiceId
  JOIN customers c ON c.CustomerId = i.CustomerId
  JOIN tracks t ON t.TrackId = ii.TrackId
  JOIN albums al ON al.AlbumId = t.AlbumId
  WHERE al.ArtistId = (SELECT ArtistId FROM artist_sales)
  GROUP BY c.CustomerId, c.FirstName
)
SELECT FirstName, amount_spent
FROM customer_spend
WHERE amount_spent < 1
ORDER BY amount_spent