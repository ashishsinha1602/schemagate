SELECT MAX(incident_count) AS max_monthly_incidents
FROM (
  SELECT EXTRACT(MONTH FROM `date`) AS month, COUNT(*) AS incident_count
  FROM `bigquery-public-data.chicago_crime.crime`
  WHERE primary_type = 'MOTOR VEHICLE THEFT'
    AND year = 2016
  GROUP BY month
)