SELECT
  d.country_name,
  SUM(d.value) AS total_long_term_external_debt
FROM `bigquery-public-data.world_bank_intl_debt.international_debt` AS d
JOIN `bigquery-public-data.world_bank_intl_debt.country_summary` AS c
  ON d.country_code = c.country_code
WHERE d.indicator_code = 'DT.DOD.DLXF.CD'
  AND c.region IS NOT NULL
  AND TRIM(c.region) != ''
  AND d.value IS NOT NULL
  AND NOT IS_NAN(d.value)
GROUP BY d.country_name
ORDER BY total_long_term_external_debt DESC
LIMIT 10