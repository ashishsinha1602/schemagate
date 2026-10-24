WITH p AS (
  SELECT
    consecutive_number,
    COUNT(DISTINCT CONCAT(CAST(vehicle_number AS STRING), '-', CAST(person_number AS STRING))) AS n_persons,
    COUNT(DISTINCT IF(injury_severity = 4, CONCAT(CAST(vehicle_number AS STRING), '-', CAST(person_number AS STRING)), NULL)) AS n_fatal
  FROM `bigquery-public-data.nhtsa_traffic_fatalities.person_2016`
  GROUP BY consecutive_number
),
v AS (
  SELECT
    consecutive_number,
    ARRAY_AGG(body_type ORDER BY vehicle_number LIMIT 1)[OFFSET(0)] AS body_type,
    AVG(IF(travel_speed <= 151 AND speed_limit <= 80, ABS(travel_speed - speed_limit), NULL)) AS avg_speed_diff
  FROM `bigquery-public-data.nhtsa_traffic_fatalities.vehicle_2016`
  GROUP BY consecutive_number
)
SELECT
  a.consecutive_number,
  IF(p.n_fatal > 1, 1, 0) AS label,
  a.state_number,
  v.body_type,
  a.number_of_drunk_drivers,
  a.day_of_week,
  a.hour_of_crash,
  IF(COALESCE(CAST(a.work_zone AS STRING), 'None') NOT IN ('None', '0'), 1, 0) AS work_zone_indicator,
  v.avg_speed_diff,
  LEAST(CAST(FLOOR(v.avg_speed_diff / 20) AS INT64), 4) AS speed_diff_level
FROM `bigquery-public-data.nhtsa_traffic_fatalities.accident_2016` a
JOIN p ON a.consecutive_number = p.consecutive_number
LEFT JOIN v ON a.consecutive_number = v.consecutive_number
WHERE p.n_persons > 1