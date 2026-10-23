WITH ParsedAirports AS (
  SELECT
    airport_code,
    city,
    CAST(SUBSTR(coordinates, 2, INSTR(coordinates, ',') - 2) AS REAL) AS longitude,
    CAST(SUBSTR(coordinates, INSTR(coordinates, ',') + 2, LENGTH(coordinates) - INSTR(coordinates, ',') - 2) AS REAL) AS latitude
  FROM main.airports_data
),
FlightCoordinates AS (
  SELECT
    dep.city AS departure_city,
    dep.latitude AS dep_lat,
    dep.longitude AS dep_lon,
    arr.city AS arrival_city,
    arr.latitude AS arr_lat,
    arr.longitude AS arr_lon
  FROM main.flights AS f
  JOIN ParsedAirports AS dep ON f.departure_airport = dep.airport_code
  JOIN ParsedAirports AS arr ON f.arrival_airport = arr.airport_code
),
FlightDistances AS (
  SELECT
    departure_city,
    arrival_city,
    -- Convert degrees to radians
    (dep_lat * 3.141592653589793 / 180.0) AS dep_lat_rad,
    (dep_lon * 3.141592653589793 / 180.0) AS dep_lon_rad,
    (arr_lat * 3.141592653589793 / 180.0) AS arr_lat_rad,
    (arr_lon * 3.141592653589793 / 180.0) AS arr_lon_rad
  FROM FlightCoordinates
),
CalculatedDistances AS (
  SELECT
    departure_city,
    arrival_city,
    6371.0 * 2 * ASIN(
      SQRT(
        POWER(SIN((arr_lat_rad - dep_lat_rad) / 2), 2) +
        COS(dep_lat_rad) * COS(arr_lat_rad) * POWER(SIN((arr_lon_rad - dep_lon_rad) / 2), 2)
      )
    ) AS distance_km
  FROM FlightDistances
),
CityPairAverageDistance AS (
  SELECT
    MIN(departure_city, arrival_city) AS city_a,
    MAX(departure_city, arrival_city) AS city_b,
    AVG(distance_km) AS average_distance
  FROM CalculatedDistances
  WHERE departure_city != arrival_city
  GROUP BY
    MIN(departure_city, arrival_city),
    MAX(departure_city, arrival_city)
),
DistanceRanges AS (
  SELECT
    CASE
      WHEN average_distance >= 0 AND average_distance < 1000 THEN '0-999'
      WHEN average_distance >= 1000 AND average_distance < 2000 THEN '1000-1999'
      WHEN average_distance >= 2000 AND average_distance < 3000 THEN '2000-2999'
      WHEN average_distance >= 3000 AND average_distance < 4000 THEN '3000-3999'
      WHEN average_distance >= 4000 AND average_distance < 5000 THEN '4000-4999'
      WHEN average_distance >= 5000 AND average_distance < 6000 THEN '5000-5999'
      ELSE '6000+'
    END AS distance_range
  FROM CityPairAverageDistance
),
RangeCounts AS (
  SELECT
    distance_range,
    COUNT(*) AS pair_count
  FROM DistanceRanges
  GROUP BY
    distance_range
)
SELECT
  MIN(pair_count)
FROM RangeCounts