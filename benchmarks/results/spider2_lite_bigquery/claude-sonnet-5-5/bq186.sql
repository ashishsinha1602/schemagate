SELECT
  FORMAT_TIMESTAMP('%Y%m', start_date) AS year_month,
  ARRAY_AGG(duration_sec / 60.0 ORDER BY start_date ASC, trip_id ASC LIMIT 1)[OFFSET(0)] AS first_trip_duration_minutes,
  ARRAY_AGG(duration_sec / 60.0 ORDER BY start_date DESC, trip_id DESC LIMIT 1)[OFFSET(0)] AS last_trip_duration_minutes,
  MAX(duration_sec) / 60.0 AS highest_trip_duration_minutes,
  MIN(duration_sec) / 60.0 AS lowest_trip_duration_minutes
FROM `bigquery-public-data.san_francisco.bikeshare_trips`
WHERE start_date IS NOT NULL AND duration_sec IS NOT NULL
GROUP BY year_month
ORDER BY year_month