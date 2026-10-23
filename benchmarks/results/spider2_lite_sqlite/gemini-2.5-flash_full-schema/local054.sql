WITH ArtistSales AS (
  SELECT
    ar.ArtistId,
    SUM(il.UnitPrice * il.Quantity) AS TotalArtistRevenue
  FROM main.artists AS ar
  JOIN main.albums AS al
    ON ar.ArtistId = al.ArtistId
  JOIN main.tracks AS t
    ON al.AlbumId = t.AlbumId
  JOIN main.invoice_items AS il
    ON t.TrackId = il.TrackId
  GROUP BY
    ar.ArtistId
), BestSellingArtist AS (
  SELECT
    ArtistId
  FROM ArtistSales
  ORDER BY
    TotalArtistRevenue DESC
  LIMIT 1
)
SELECT
  c.FirstName,
  SUM(il.UnitPrice * il.Quantity) AS TotalSpent
FROM main.customers AS c
JOIN main.invoices AS i
  ON c.CustomerId = i.CustomerId
JOIN main.invoice_items AS il
  ON i.InvoiceId = il.InvoiceId
JOIN main.tracks AS t
  ON il.TrackId = t.TrackId
JOIN main.albums AS al
  ON t.AlbumId = al.AlbumId
WHERE
  al.ArtistId = (
    SELECT
      ArtistId
    FROM BestSellingArtist
  )
GROUP BY
  c.CustomerId,
  c.FirstName
HAVING
  SUM(il.UnitPrice * il.Quantity) < 1