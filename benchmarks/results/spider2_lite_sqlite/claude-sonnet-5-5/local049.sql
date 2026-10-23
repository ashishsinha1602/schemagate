WITH c AS (
  SELECT i.industry, COUNT(DISTINCT d.company_id) AS total_new
  FROM companies_industries i
  JOIN companies_dates d ON d.company_id = i.company_id
  WHERE CAST(strftime('%Y', d.date_joined) AS INTEGER) BETWEEN 2019 AND 2021
  GROUP BY i.industry
)
SELECT industry, total_new, total_new / 3.0 AS avg_new_per_year
FROM c
ORDER BY total_new DESC
LIMIT 1