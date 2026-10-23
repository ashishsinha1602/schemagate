WITH ap AS (
  SELECT airport_code, city,
         CAST(substr(coordinates, 2, instr(coordinates, ',') - 2) AS REAL) AS lon,
         CAST(substr(coordinates, instr(coordinates, ',') + 1) AS REAL) AS lat
  FROM airports_data
),
fl AS (
  SELECT d.city AS from_city, a.city AS to_city,
         d.lon AS lon1, d.lat AS lat1, a.lon AS lon2, a.lat AS lat2
  FROM flights f
  JOIN ap d ON d.airport_code = f.departure_airport
  JOIN ap a ON a.airport_code = f.arrival_airport
),
dist AS (
  SELECT CASE WHEN from_city < to_city THEN from_city ELSE to_city END AS city1,
         CASE WHEN from_city < to_city THEN to_city ELSE from_city END AS city2,
         2 * 6371 * asin(sqrt(
           sin((lat2 - lat1) * 3.14159265358979 / 360) * sin((lat2 - lat1) * 3.14159265358979 / 360)
           + cos(lat1 * 3.14159265358979 / 180) * cos(lat2 * 3.14159265358979 / 180)
             * sin((lon2 - lon1) * 3.14159265358979 / 360) * sin((lon2 - lon1) * 3.14159265358979 / 360)
         )) AS d
  FROM fl
),
pairs AS (
  SELECT city1, city2, AVG(d) AS avg_d
  FROM dist
  GROUP BY city1, city2
),
buckets AS (
  SELECT CASE WHEN avg_d >= 6000 THEN '6000+'
              ELSE CAST(CAST(avg_d / 1000 AS INTEGER) * 1000 AS TEXT) END AS range_bucket,
         COUNT(*) AS pair_count
  FROM pairs
  GROUP BY 1
)
SELECT pair_count
FROM buckets
ORDER BY pair_count ASC
LIMIT 1