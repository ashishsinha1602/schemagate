WITH cand AS (
  SELECT
    s.id,
    ST_DISTANCE(ST_GEOGPOINT(s.longitude, s.latitude), ST_GEOGPOINT(-74.0060, 40.7128)) AS dist
  FROM `bigquery-public-data.ghcn_d.ghcnd_stations` s
  WHERE ST_DISTANCE(ST_GEOGPOINT(s.longitude, s.latitude), ST_GEOGPOINT(-74.0060, 40.7128)) <= 50000
),
w AS (
  SELECT g.id, g.date, g.value
  FROM `bigquery-public-data.ghcn_d.ghcnd_*` g
  JOIN cand c ON g.id = c.id
  WHERE _TABLE_SUFFIX = '2016'
    AND g.element = 'PRCP'
    AND g.qflag IS NULL
    AND g.value IS NOT NULL
),
best AS (
  SELECT c.id
  FROM cand c
  WHERE c.id IN (SELECT id FROM w)
  ORDER BY c.dist
  LIMIT 1
),
daily_weather AS (
  SELECT date, SUM(value) / 10 AS prcp_mm
  FROM w
  WHERE id IN (SELECT id FROM best)
  GROUP BY date
),
daily_trips AS (
  SELECT DATE(starttime) AS date, COUNT(*) AS trips
  FROM `bigquery-public-data.new_york.citibike_trips`
  WHERE EXTRACT(YEAR FROM starttime) = 2016
  GROUP BY date
)
SELECT
  IF(dw.prcp_mm > 5, 'rainy', 'non-rainy') AS weather_condition,
  AVG(dt.trips) AS avg_daily_trips
FROM daily_trips dt
JOIN daily_weather dw ON dt.date = dw.date
GROUP BY weather_condition