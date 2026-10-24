WITH ordered AS (
  SELECT
    geolocation_state,
    geolocation_city,
    geolocation_zip_code_prefix,
    geolocation_lat,
    geolocation_lng,
    LAG(geolocation_state) OVER w AS prev_state,
    LAG(geolocation_city) OVER w AS prev_city,
    LAG(geolocation_zip_code_prefix) OVER w AS prev_zip,
    LAG(geolocation_lat) OVER w AS prev_lat,
    LAG(geolocation_lng) OVER w AS prev_lng
  FROM main.olist_geolocation
  WINDOW w AS (
    ORDER BY geolocation_state, geolocation_city, geolocation_zip_code_prefix,
             geolocation_lat, geolocation_lng
  )
),
dist AS (
  SELECT
    prev_state, prev_city, prev_zip,
    geolocation_state, geolocation_city, geolocation_zip_code_prefix,
    6371 * acos(
      MIN(1.0, MAX(-1.0,
        cos(prev_lat * 3.141592653589793 / 180) * cos(geolocation_lat * 3.141592653589793 / 180)
        * cos((geolocation_lng - prev_lng) * 3.141592653589793 / 180)
        + sin(prev_lat * 3.141592653589793 / 180) * sin(geolocation_lat * 3.141592653589793 / 180)
      ))
    ) AS distance_km
  FROM ordered
  WHERE prev_lat IS NOT NULL
)
SELECT
  prev_state AS city1_state,
  prev_city AS city1,
  prev_zip AS city1_zip_code_prefix,
  geolocation_state AS city2_state,
  geolocation_city AS city2,
  geolocation_zip_code_prefix AS city2_zip_code_prefix,
  distance_km
FROM dist
ORDER BY distance_km DESC
LIMIT 1