WITH yearly AS (
  SELECT ci.industry,
         CAST(substr(cd.date_joined, 1, 4) AS INTEGER) AS yr,
         COUNT(*) AS n
  FROM companies_industries ci
  JOIN companies_dates cd ON cd.company_id = ci.company_id
  WHERE CAST(substr(cd.date_joined, 1, 4) AS INTEGER) BETWEEN 2019 AND 2021
  GROUP BY ci.industry, yr
),
top_industry AS (
  SELECT industry
  FROM yearly
  GROUP BY industry
  ORDER BY SUM(n) DESC
  LIMIT 1
)
SELECT y.industry,
       SUM(y.n) / 3.0 AS avg_new_unicorns_per_year
FROM yearly y
JOIN top_industry t ON t.industry = y.industry
GROUP BY y.industry