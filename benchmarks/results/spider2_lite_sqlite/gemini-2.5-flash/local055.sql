WITH ArtistSales AS (
    SELECT
        ar.ArtistId,
        ar.Name AS ArtistName,
        SUM(ii.UnitPrice * ii.Quantity) AS TotalSales
    FROM main.artists AS ar
    JOIN main.albums AS al ON ar.ArtistId = al.ArtistId
    JOIN main.tracks AS t ON al.AlbumId = t.AlbumId
    JOIN main.invoice_items AS ii ON t.TrackId = ii.TrackId
    GROUP BY ar.ArtistId, ar.Name
),
TopSellingArtist AS (
    SELECT
        ArtistId
    FROM ArtistSales
    ORDER BY TotalSales DESC, ArtistName ASC
    LIMIT 1
),
LowestSellingArtist AS (
    SELECT
        ArtistId
    FROM ArtistSales
    ORDER BY TotalSales ASC, ArtistName ASC
    LIMIT 1
),
CustomerSpendingTopArtist AS (
    SELECT
        i.CustomerId,
        SUM(ii.UnitPrice * ii.Quantity) AS CustomerTotalSpending
    FROM main.invoices AS i
    JOIN main.invoice_items AS ii ON i.InvoiceId = ii.InvoiceId
    JOIN main.tracks AS t ON ii.TrackId = t.TrackId
    JOIN main.albums AS al ON t.AlbumId = al.AlbumId
    JOIN TopSellingArtist AS tsa ON al.ArtistId = tsa.ArtistId
    GROUP BY i.CustomerId
),
CustomerSpendingLowestArtist AS (
    SELECT
        i.CustomerId,
        SUM(ii.UnitPrice * ii.Quantity) AS CustomerTotalSpending
    FROM main.invoices AS i
    JOIN main.invoice_items AS ii ON i.InvoiceId = ii.InvoiceId
    JOIN main.tracks AS t ON ii.TrackId = t.TrackId
    JOIN main.albums AS al ON t.AlbumId = al.AlbumId
    JOIN LowestSellingArtist AS lsa ON al.ArtistId = lsa.ArtistId
    GROUP BY i.CustomerId
)
SELECT
    ABS(
        (SELECT AVG(CustomerTotalSpending) FROM CustomerSpendingTopArtist) -
        (SELECT AVG(CustomerTotalSpending) FROM CustomerSpendingLowestArtist)
    )