WITH a AS (
  SELECT state_number, state_name, consecutive_number, year_of_crash
  FROM `bigquery-public-data.nhtsa_traffic_fatalities.accident_*`
  WHERE _TABLE_SUFFIX IN ('2015', '2016')
),
d AS (
  SELECT DISTINCT state_number, consecutive_number, _TABLE_SUFFIX AS yr
  FROM `bigquery-public-data.nhtsa_traffic_fatalities.distract_*`
  WHERE _TABLE_SUFFIX IN ('2015', '2016')
    AND driver_distracted_by_name NOT IN ('Not Distracted', 'Unknown if Distracted', 'Not Reported')
),
c AS (
  SELECT a.year_of_crash, a.state_name, COUNT(DISTINCT a.consecutive_number) AS distracted_accidents
  FROM a
  JOIN d
    ON a.state_number = d.state_number
   AND a.consecutive_number = d.consecutive_number
   AND CAST(a.year_of_crash AS STRING) = d.yr
  GROUP BY a.year_of_crash, a.state_name
)
SELECT year_of_crash, state_name, distracted_accidents
FROM c
QUALIFY ROW_NUMBER() OVER (PARTITION BY year_of_crash ORDER BY distracted_accidents DESC) <= 5
ORDER BY year_of_crash, distracted_accidents DESC