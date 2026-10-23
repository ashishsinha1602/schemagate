WITH f AS (
  SELECT
    CAST(substr(d.coordinates, 2, instr(d.coordinates, ',') - 2) AS REAL) AS lon1,
    CAST(substr(d.coordinates, instr(d.coordinates, ',') + 1, length(d.coordinates) - instr(d.coordinates, ',') - 1) AS REAL) AS lat1,
    CAST(substr(a.coordinates, 2, instr(a.coordinates, ',') - 2) AS REAL) AS lon2,
    CAST(substr(a.coordinates, instr(a.coordinates, ',') + 1, length(a.coordinates) - instr(a.coordinates, ',') - 1) AS REAL) AS lat2
  FROM flights fl
  JOIN airports_data d ON fl.departure_airport = d.airport_code
  JOIN airports_data a ON fl.arrival_airport = a.airport_code
  WHERE d.city LIKE '%Abakan%' OR a.city LIKE '%Abakan%'
),
g AS (
  SELECT
    lat1 * 3.141592653589793 / 180 AS p1,
    lat2 * 3.141592653589793 / 180 AS p2,
    (lat2 - lat1) * 3.141592653589793 / 180 AS dp,
    (lon2 - lon1) * 3.141592653589793 / 180 AS dl
  FROM f
)
SELECT MAX(2 * 6371 * asin(sqrt(sin(dp / 2) * sin(dp / 2) + cos(p1) * cos(p2) * sin(dl / 2) * sin(dl / 2)))) AS max_distance_km
FROM g