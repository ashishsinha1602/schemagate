WITH RECURSIVE periods(period) AS (
  SELECT 1
  UNION ALL
  SELECT period + 1 FROM periods WHERE period < 20
),
first_terms AS (
  SELECT id_bioguide, MIN(term_start) AS first_start
  FROM legislators_terms
  GROUP BY id_bioguide
),
cohort AS (
  SELECT id_bioguide, first_start
  FROM first_terms
  WHERE first_start BETWEEN '1917-01-01' AND '1999-12-31'
),
cohort_size AS (
  SELECT COUNT(*) AS n FROM cohort
),
retained AS (
  SELECT p.period, COUNT(DISTINCT c.id_bioguide) AS retained_count
  FROM periods p
  CROSS JOIN cohort c
  JOIN legislators_terms t
    ON t.id_bioguide = c.id_bioguide
   AND t.term_start <= (CAST(CAST(strftime('%Y', c.first_start) AS INTEGER) + p.period - 1 AS TEXT) || '-12-31')
   AND t.term_end >= (CAST(CAST(strftime('%Y', c.first_start) AS INTEGER) + p.period - 1 AS TEXT) || '-12-31')
  GROUP BY p.period
)
SELECT p.period,
       cs.n AS cohort_size,
       COALESCE(r.retained_count, 0) AS retained_count,
       CAST(COALESCE(r.retained_count, 0) AS REAL) / cs.n AS retention_rate
FROM periods p
CROSS JOIN cohort_size cs
LEFT JOIN retained r ON r.period = p.period
ORDER BY p.period