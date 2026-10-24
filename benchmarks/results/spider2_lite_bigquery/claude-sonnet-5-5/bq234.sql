WITH s AS (
  SELECT nppes_provider_state AS state, drug_name, SUM(total_claim_count) AS total_claims
  FROM `bigquery-public-data.cms_medicare.part_d_prescriber_2014`
  GROUP BY nppes_provider_state, drug_name
)
SELECT state, drug_name, total_claims
FROM (
  SELECT state, drug_name, total_claims,
         RANK() OVER (PARTITION BY state ORDER BY total_claims DESC) AS rnk
  FROM s
)
WHERE rnk = 1
ORDER BY state