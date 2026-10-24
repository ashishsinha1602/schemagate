WITH base AS (
  SELECT minor_category, year, SUM(value) AS v
  FROM `bigquery-public-data.london_crime.crime_by_lsoa`
  WHERE year >= 2008
  GROUP BY minor_category, year
),
ranked AS (
  SELECT minor_category, ROW_NUMBER() OVER (ORDER BY SUM(v) DESC) AS rn
  FROM base
  GROUP BY minor_category
),
yt AS (
  SELECT year, SUM(v) AS total
  FROM base
  GROUP BY year
)
SELECT
  b.year,
  ROUND(100 * SAFE_DIVIDE(SUM(IF(r.rn = 1, b.v, 0)), yt.total), 2) AS top1_pct,
  ROUND(100 * SAFE_DIVIDE(SUM(IF(r.rn = 2, b.v, 0)), yt.total), 2) AS top2_pct,
  ROUND(100 * SAFE_DIVIDE(SUM(IF(r.rn = 3, b.v, 0)), yt.total), 2) AS top3_pct,
  ROUND(100 * SAFE_DIVIDE(SUM(IF(r.rn = 4, b.v, 0)), yt.total), 2) AS top4_pct,
  ROUND(100 * SAFE_DIVIDE(SUM(IF(r.rn = 5, b.v, 0)), yt.total), 2) AS top5_pct
FROM base b
JOIN ranked r ON b.minor_category = r.minor_category AND r.rn <= 5
JOIN yt ON b.year = yt.year
GROUP BY b.year, yt.total
ORDER BY b.year