WITH RankedLocations AS (
    SELECT
        geolocation_state,
        geolocation_city,
        geolocation_zip_code_prefix,
        geolocation_lat,
        geolocation_lng,
        LAG(geolocation_city) OVER (ORDER BY geolocation_state, geolocation_city, geolocation_zip_code_prefix, geolocation_lat, geolocation_lng) AS prev_geolocation_city,
        LAG(geolocation_lat) OVER (ORDER BY geolocation_state, geolocation_city, geolocation_zip_code_prefix, geolocation_lat, geolocation_lng) AS prev_geolocation_lat,
        LAG(geolocation_lng) OVER (ORDER BY geolocation_state, geolocation_city, geolocation_zip_code_prefix, geolocation_lat, geolocation_lng) AS prev_geolocation_lng
    FROM
        main.olist_geolocation
),
RadiansConverted AS (
    SELECT
        geolocation_city AS city2_name,
        prev_geolocation_city AS city1_name,
        (geolocation_lat * PI() / 180.0) AS lat2_rad,
        (geolocation_lng * PI() / 180.0) AS lon2_rad,
        (prev_geolocation_lat * PI() / 180.0) AS lat1_rad,
        (prev_geolocation_lng * PI() / 180.0) AS lon1_rad
    FROM
        RankedLocations
    WHERE
        prev_geolocation_lat IS NOT NULL
)
SELECT
    T1.city1_name,
    T1.city2_name
FROM
    RadiansConverted AS T1
ORDER BY
    6371 * ACOS(
        MAX(-1.0, MIN(1.0,
            COS(T1.lat1_rad) * COS(T1.lat2_rad) * COS(T1.lon2_rad - T1.lon1_rad) +
            SIN(T1.lat1_rad) * SIN(T1.lat2_rad)
        ))
    ) DESC
LIMIT 1