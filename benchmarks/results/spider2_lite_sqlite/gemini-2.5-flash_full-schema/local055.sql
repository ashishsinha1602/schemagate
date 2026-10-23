WITH ArtistSales AS (
    SELECT
        ar.ArtistId,
        ar.Name AS ArtistName,
        SUM(ii.UnitPrice * ii.Quantity) AS TotalSales
    FROM main.artists AS ar
    JOIN main.albums AS al ON ar.ArtistId = al.ArtistId
    JOIN main.tracks AS t ON al.AlbumId = t.AlbumId
    JOIN main.invoice_items AS ii ON t.TrackId = ii.TrackId
    GROUP BY
        ar.ArtistId,
        ar.Name
),
RankedArtistSales AS (
    SELECT
        ArtistId,
        ArtistName,
        TotalSales,
        RANK() OVER (ORDER BY TotalSales DESC, ArtistName ASC) AS RankDesc,
        RANK() OVER (ORDER BY TotalSales ASC, ArtistName ASC) AS RankAsc
    FROM ArtistSales
),
IdentifiedArtists AS (
    SELECT ArtistId, 'Top' AS ArtistType FROM RankedArtistSales WHERE RankDesc = 1
    UNION ALL
    SELECT ArtistId, 'Lowest' AS ArtistType FROM RankedArtistSales WHERE RankAsc = 1
),
CustomerSpendingPerArtist AS (
    SELECT
        c.CustomerId,
        ia.ArtistType,
        SUM(ii.UnitPrice * ii.Quantity) AS AmountSpent
    FROM main.customers AS c
    JOIN main.invoices AS i ON c.CustomerId = i.CustomerId
    JOIN main.invoice_items AS ii ON i.InvoiceId = ii.InvoiceId
    JOIN main.tracks AS t ON ii.TrackId = t.TrackId
    JOIN main.albums AS al ON t.AlbumId = al.AlbumId
    JOIN main.artists AS ar ON al.ArtistId = ar.ArtistId
    JOIN IdentifiedArtists AS ia ON ar.ArtistId = ia.ArtistId
    GROUP BY
        c.CustomerId,
        ia.ArtistType
),
AverageSpending AS (
    SELECT
        ArtistType,
        AVG(AmountSpent) AS AverageAmount
    FROM CustomerSpendingPerArtist
    GROUP BY
        ArtistType
)
SELECT
    ABS(
        (SELECT AverageAmount FROM AverageSpending WHERE ArtistType = 'Top') -
        (SELECT AverageAmount FROM AverageSpending WHERE ArtistType = 'Lowest')
    )