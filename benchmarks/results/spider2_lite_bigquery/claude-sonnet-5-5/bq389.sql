WITH u AS (
  SELECT date_local, 'pm10' AS p, arithmetic_mean AS v
  FROM `bigquery-public-data.epa_historical_air_quality.pm10_daily_summary`
  WHERE state_name = 'California' AND EXTRACT(YEAR FROM date_local) = 2020
  UNION ALL
  SELECT date_local, 'pm25_frm', arithmetic_mean
  FROM `bigquery-public-data.epa_historical_air_quality.pm25_frm_daily_summary`
  WHERE state_name = 'California' AND EXTRACT(YEAR FROM date_local) = 2020
  UNION ALL
  SELECT date_local, 'pm25_nonfrm', arithmetic_mean
  FROM `bigquery-public-data.epa_historical_air_quality.pm25_nonfrm_daily_summary`
  WHERE state_name = 'California' AND EXTRACT(YEAR FROM date_local) = 2020
  UNION ALL
  SELECT date_local, 'so2', arithmetic_mean * 10
  FROM `bigquery-public-data.epa_historical_air_quality.so2_daily_summary`
  WHERE state_name = 'California' AND EXTRACT(YEAR FROM date_local) = 2020
  UNION ALL
  SELECT date_local, 'lead', arithmetic_mean * 100
  FROM `bigquery-public-data.epa_historical_air_quality.lead_daily_summary`
  WHERE state_name = 'California' AND EXTRACT(YEAR FROM date_local) = 2020
)
SELECT
  EXTRACT(MONTH FROM date_local) AS month,
  AVG(IF(p = 'pm10', v, NULL)) AS pm10_avg,
  AVG(IF(p = 'pm25_frm', v, NULL)) AS pm25_frm_avg,
  AVG(IF(p = 'pm25_nonfrm', v, NULL)) AS pm25_nonfrm_avg,
  AVG(IF(p = 'so2', v, NULL)) AS so2_avg_x10,
  AVG(IF(p = 'lead', v, NULL)) AS lead_avg_x100
FROM u
GROUP BY month
ORDER BY month