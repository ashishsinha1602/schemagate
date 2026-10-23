WITH RankedLocations AS (
    SELECT
        geolocation_zip_code_prefix,
        geolocation_lat,
        geolocation_lng,
        geolocation_city,
        geolocation_state,
        geolocation_lat * PI() / 180.0 AS lat_rad,
        geolocation_lng * PI() / 180.0 AS lng_rad,
        LAG(geolocation_lat * PI() / 180.0, 1, NULL) OVER (
            ORDER BY
                geolocation_state,
                geolocation_city,
                geolocation_zip_code_prefix,
                geolocation_lat,
                geolocation_lng
        ) AS prev_lat_rad,
        LAG(geolocation_lng * PI() / 180.0, 1, NULL) OVER (
            ORDER BY
                geolocation_state,
                geolocation_city,
                geolocation_zip_code_prefix,
                geolocation_lat,
                geolocation_lng
        ) AS prev_lng_rad,
        LAG(geolocation_city, 1, NULL) OVER (
            ORDER BY
                geolocation_state,
                geolocation_city,
                geolocation_zip_code_prefix,
                geolocation_lat,
                geolocation_lng
        ) AS prev_city,
        LAG(geolocation_state, 1, NULL) OVER (
            ORDER BY
                geolocation_state,
                geolocation_city,
                geolocation_zip_code_prefix,
                geolocation_lat,
                geolocation_lng
        ) AS prev_state,
        LAG(geolocation_zip_code_prefix, 1, NULL) OVER (
            ORDER BY
                geolocation_state,
                geolocation_city,
                geolocation_zip_code_prefix,
                geolocation_lat,
                geolocation_lng
        ) AS prev_zip_code_prefix
    FROM
        main.olist_geolocation
),
Distances AS (
    SELECT
        geolocation_zip_code_prefix,
        geolocation_lat,
        geolocation_lng,
        geolocation_city,
        geolocation_state,
        prev_zip_code_prefix,
        prev_city,
        prev_state,
        (
            6371 * ACOS(
                MAX(-1.0, MIN(1.0,
                    COS(lat_rad) * COS(prev_lat_rad) * COS(lng_rad - prev_lng_rad) +
                    SIN(lat_rad) * SIN(prev_lat_rad)
                ))
            )
        ) AS distance_km
    FROM
        RankedLocations
    WHERE
        prev_lat_rad IS NOT NULL
)
SELECT
    prev_state,
    prev_city,
    prev_zip_code_prefix,
    geolocation_state,
    geolocation_city,
    geolocation_zip_code_prefix,
    distance_km
FROM
    Distances
ORDER BY
    distance_km DESC
LIMIT 1