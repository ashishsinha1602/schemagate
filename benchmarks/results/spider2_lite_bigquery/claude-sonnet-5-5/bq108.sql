SELECT
  SAFE_DIVIDE(COUNTIF(number_of_fatalities > 1), COUNT(*)) * 100 AS percentage
FROM `bigquery-public-data.nhtsa_traffic_fatalities.accident_*`
WHERE _TABLE_SUFFIX = '2015'
  AND month_of_crash BETWEEN 1 AND 8
  AND (COALESCE(number_of_forms_submitted_for_persons_in_motor_vehicles, 0) + COALESCE(number_of_forms_submitted_for_persons_not_in_motor_vehicles, 0)) > 1