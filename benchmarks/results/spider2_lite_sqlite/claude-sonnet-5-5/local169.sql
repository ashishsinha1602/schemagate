WITH first_terms AS (
  SELECT id_bioguide, MIN(term_start) AS first_start
  FROM legislators_terms
  GROUP BY id_bioguide
  HAVING MIN(term_start) BETWEEN '1917-01-01' AND '1999-12-31'
),
periods(n) AS (
  SELECT 1
  UNION ALL
  SELECT n + 1 FROM periods WHERE n < 20
),
cohort AS (
  SELECT COUNT(*) AS total FROM first_terms
)
SELECT
  p.n AS years_after_first_term,
  COUNT(DISTINCT t.id_bioguide) AS retained_legislators,
  c.total AS cohort_size,
  CASE WHEN c.total = 0 THEN 0.0 ELSE 1.0 * COUNT(DISTINCT t.id_bioguide) / c.total END AS retention_rate
FROM periods p
CROSS JOIN cohort c
LEFT JOIN first_terms f ON 1 = 1
LEFT JOIN legislators_terms t
  ON t.id_bioguide = f.id_bioguide
  AND t.term_start <= (CAST(strftime('%Y', f.first_start) AS INTEGER) + p.n) || '-12-31'
  AND t.term_end >= (CAST(strftime('%Y', f.first_start) AS INTEGER) + p.n) || '-12-31'
GROUP BY p.n, c.total
ORDER BY p.n