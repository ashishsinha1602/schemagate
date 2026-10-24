WITH ap AS (
  SELECT airport_code,
         json_extract(city, '$.en') AS city_name,
         CAST(substr(coordinates, 2, instr(coordinates, ',') - 2) AS REAL) AS lon,
         CAST(substr(coordinates, instr(coordinates, ',') + 1,
                     length(coordinates) - instr(coordinates, ',') - 1) AS REAL) AS lat
  FROM airports_data
),
fd AS (
  SELECT CASE WHEN d.city_name < a.city_name THEN d.city_name ELSE a.city_name END AS city1,
         CASE WHEN d.city_name < a.city_name THEN a.city_name ELSE d.city_name END AS city2,
         2 * 6371 * asin(sqrt(
           power(sin((a.lat - d.lat) * pi() / 180 / 2), 2) +
           cos(d.lat * pi() / 180) * cos(a.lat * pi() / 180) *
           power(sin((a.lon - d.lon) * pi() / 180 / 2), 2)
         )) AS dist
  FROM flights f
  JOIN ap d ON d.airport_code = f.departure_airport
  JOIN ap a ON a.airport_code = f.arrival_airport
  WHERE d.city_name = 'Abakan' OR a.city_name = 'Abakan'
),
routes AS (
  SELECT city1, city2, AVG(dist) AS avg_dist
  FROM fd
  GROUP BY city1, city2
)
SELECT MAX(avg_dist) AS longest_route_km
FROM routes