WITH dedup AS (
  SELECT DISTINCT * FROM `data-to-insights.ecommerce.rev_transactions`
),
cc AS (
  SELECT channelGrouping, geoNetwork_country AS country, SUM(totals_transactions) AS country_tx
  FROM dedup
  WHERE totals_transactions IS NOT NULL
  GROUP BY channelGrouping, geoNetwork_country
),
ranked AS (
  SELECT
    channelGrouping,
    country,
    country_tx,
    SUM(country_tx) OVER (PARTITION BY channelGrouping) AS total_transactions,
    COUNT(country) OVER (PARTITION BY channelGrouping) AS country_count,
    ROW_NUMBER() OVER (PARTITION BY channelGrouping ORDER BY country_tx DESC) AS rn
  FROM cc
)
SELECT channelGrouping, country, total_transactions
FROM ranked
WHERE country_count > 1 AND rn = 1