SELECT COUNT(*) AS indicator_count
FROM `bigquery-public-data.world_bank_intl_debt.international_debt`
WHERE country_name = 'Russian Federation'
  AND value = 0