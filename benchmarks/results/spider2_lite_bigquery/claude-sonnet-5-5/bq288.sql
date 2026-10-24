WITH top_state AS (
  SELECT i.state_name, SUM(i.total_assets) AS total_assets_sum
  FROM `bigquery-public-data.fdic_banks.institutions` i
  JOIN `bigquery-public-data.fdic_banks.locations` l
    ON i.fdic_certificate_number = l.fdic_certificate_number
  WHERE l.main_office = TRUE
    AND l.date_established BETWEEN DATE '1900-01-01' AND DATE '2000-12-31'
    AND i.institution_name LIKE 'Bank%'
  GROUP BY i.state_name
  ORDER BY total_assets_sum DESC
  LIMIT 1
)
SELECT COUNT(DISTINCT i.fdic_certificate_number) AS total_institutions
FROM `bigquery-public-data.fdic_banks.institutions` i
JOIN top_state t
  ON i.state_name = t.state_name