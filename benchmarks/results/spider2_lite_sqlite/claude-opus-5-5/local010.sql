WITH flight_coords AS (
  SELECT
    dep.city AS from_city,
    arr.city AS to_city,
    CAST(substr(dep.coordinates, 2, instr(dep.coordinates, ',') - 2) AS REAL) AS lon1,
    CAST(substr(dep.coordinates, instr(dep.coordinates, ',') + 1, length(dep.coordinates) - instr(dep.coordinates, ',') - 1) AS REAL) AS lat1,
    CAST(substr(arr.coordinates, 2, instr(arr.coordinates, ',') - 2) AS REAL) AS lon2,
    CAST(substr(arr.coordinates, instr(arr.coordinates, ',') + 1, length(arr.coordinates) - instr(arr.coordinates, ',') - 1) AS REAL) AS lat2
  FROM flights f
  JOIN airports_data dep ON f.departure_airport = dep.airport_code
  JOIN airports_data arr ON f.arrival_airport = arr.airport_code
),
flight_dist AS (
  SELECT
    CASE WHEN from_city < to_city THEN from_city ELSE to_city END AS city1,
    CASE WHEN from_city < to_city THEN to_city ELSE from_city END AS city2,
    2 * 6371 * asin(sqrt(
      power(sin(radians(lat2 - lat1) / 2), 2)
      + cos(radians(lat1)) * cos(radians(lat2)) * power(sin(radians(lon2 - lon1) / 2), 2)
    )) AS distance
  FROM flight_coords
),
pair_avg AS (
  SELECT city1, city2, AVG(distance) AS avg_distance
  FROM flight_dist
  GROUP BY city1, city2
),
binned AS (
  SELECT
    CASE WHEN avg_distance >= 6000 THEN 6000
         ELSE CAST(avg_distance / 1000 AS INTEGER) * 1000 END AS distance_range
  FROM pair_avg
),
range_counts AS (
  SELECT distance_range, COUNT(*) AS pair_count
  FROM binned
  GROUP BY distance_range
)
SELECT MIN(pair_count) AS pair_count
FROM range_counts