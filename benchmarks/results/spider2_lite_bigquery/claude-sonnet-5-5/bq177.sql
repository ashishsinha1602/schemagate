WITH inp AS (
  SELECT provider_id, _TABLE_SUFFIX AS yr, average_medicare_payments * total_discharges AS cost
  FROM `bigquery-public-data.cms_medicare.inpatient_charges_*`
  WHERE _TABLE_SUFFIX BETWEEN '2011' AND '2015'
),
top_provider AS (
  SELECT provider_id
  FROM inp
  GROUP BY provider_id
  ORDER BY SUM(cost) DESC
  LIMIT 1
),
inp_year AS (
  SELECT i.provider_id, i.yr, AVG(i.cost) AS avg_inpatient_cost
  FROM inp i
  JOIN top_provider t ON i.provider_id = t.provider_id
  GROUP BY i.provider_id, i.yr
),
out_year AS (
  SELECT o.provider_id, o._TABLE_SUFFIX AS yr, AVG(o.average_total_payments * o.outpatient_services) AS avg_outpatient_cost
  FROM `bigquery-public-data.cms_medicare.outpatient_charges_*` o
  JOIN top_provider t ON o.provider_id = t.provider_id
  WHERE o._TABLE_SUFFIX BETWEEN '2011' AND '2015'
  GROUP BY o.provider_id, o._TABLE_SUFFIX
)
SELECT
  i.provider_id,
  i.yr AS year,
  i.avg_inpatient_cost,
  o.avg_outpatient_cost
FROM inp_year i
LEFT JOIN out_year o ON i.provider_id = o.provider_id AND i.yr = o.yr
ORDER BY i.yr