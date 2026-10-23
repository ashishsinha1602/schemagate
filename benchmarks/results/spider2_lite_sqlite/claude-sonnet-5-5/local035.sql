WITH ordered AS (
  SELECT
    geolocation_state,
    geolocation_city,
    geolocation_lat,
    geolocation_lng,
    LAG(geolocation_city) OVER w AS prev_city,
    LAG(geolocation_state) OVER w AS prev_state,
    LAG(geolocation_lat) OVER w AS prev_lat,
    LAG(geolocation_lng) OVER w AS prev_lng
  FROM main.olist_geolocation
  WINDOW w AS (ORDER BY geolocation_state, geolocation_city, geolocation_zip_code_prefix, geolocation_lat, geolocation_lng)
),
dist AS (
  SELECT
    prev_state,
    prev_city,
    geolocation_state,
    geolocation_city,
    6371 * acos(
      min(1.0, max(-1.0,
        cos(radians(prev_lat)) * cos(radians(geolocation_lat)) * cos(radians(geolocation_lng) - radians(prev_lng))
        + sin(radians(prev_lat)) * sin(radians(geolocation_lat))
      ))
    ) AS distance_km
  FROM ordered
  WHERE prev_lat IS NOT NULL
)
SELECT
  prev_state,
  prev_city,
  geolocation_state AS state,
  geolocation_city AS city,
  distance_km
FROM dist
ORDER BY distance_km DESC
LIMIT 1