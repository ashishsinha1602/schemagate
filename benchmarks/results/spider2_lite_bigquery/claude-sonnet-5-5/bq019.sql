WITH top_drg AS (
  SELECT drg_definition
  FROM `bigquery-public-data.cms_medicare.inpatient_charges_*`
  WHERE _TABLE_SUFFIX = '2014'
  GROUP BY drg_definition
  ORDER BY SUM(total_discharges) DESC
  LIMIT 1
)
SELECT
  t.provider_city,
  SAFE_DIVIDE(SUM(t.average_total_payments * t.total_discharges), SUM(t.total_discharges)) AS weighted_avg_total_payments
FROM `bigquery-public-data.cms_medicare.inpatient_charges_*` t
JOIN top_drg d ON t.drg_definition = d.drg_definition
WHERE t._TABLE_SUFFIX = '2014'
GROUP BY t.provider_city
ORDER BY SUM(t.total_discharges) DESC
LIMIT 3