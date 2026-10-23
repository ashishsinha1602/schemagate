WITH GlobalDurationStats AS (
    SELECT
        MIN(T.Milliseconds / 60000.0) AS MinDuration,
        MAX(T.Milliseconds / 60000.0) AS MaxDuration,
        AVG(T.Milliseconds / 60000.0) AS AvgDuration
    FROM main.Track AS T
),
TrackDetailsWithRevenue AS (
    SELECT
        T.TrackId,
        T.Milliseconds / 60000.0 AS DurationMinutes,
        SUM(COALESCE(IL.UnitPrice * IL.Quantity, 0)) AS TotalTrackRevenue
    FROM main.Track AS T
    LEFT JOIN main.InvoiceLine AS IL
        ON T.TrackId = IL.TrackId
    GROUP BY
        T.TrackId,
        T.Milliseconds
)
SELECT
    CASE
        WHEN TD.DurationMinutes >= GDS.MinDuration AND TD.DurationMinutes < (GDS.MinDuration + GDS.AvgDuration) / 2.0 THEN 'Short'
        WHEN TD.DurationMinutes >= (GDS.MinDuration + GDS.AvgDuration) / 2.0 AND TD.DurationMinutes < (GDS.AvgDuration + GDS.MaxDuration) / 2.0 THEN 'Medium'
        WHEN TD.DurationMinutes >= (GDS.AvgDuration + GDS.MaxDuration) / 2.0 AND TD.DurationMinutes <= GDS.MaxDuration THEN 'Long'
        ELSE 'Unknown'
    END AS Category,
    MIN(TD.DurationMinutes) AS MinDurationCategory,
    MAX(TD.DurationMinutes) AS MaxDurationCategory,
    SUM(TD.TotalTrackRevenue) AS TotalRevenueCategory
FROM TrackDetailsWithRevenue AS TD
CROSS JOIN GlobalDurationStats AS GDS
GROUP BY Category
ORDER BY
    CASE Category
        WHEN 'Short' THEN 1
        WHEN 'Medium' THEN 2
        WHEN 'Long' THEN 3
        ELSE 4
    END