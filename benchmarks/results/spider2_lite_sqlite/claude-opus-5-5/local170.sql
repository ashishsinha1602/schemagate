WITH RECURSIVE periods(p) AS (
  SELECT 0
  UNION ALL
  SELECT p + 2 FROM periods WHERE p < 10
),
first_term AS (
  SELECT id_bioguide, MIN(term_start) AS first_start
  FROM legislators_terms
  GROUP BY id_bioguide
),
cohort AS (
  SELECT f.id_bioguide,
         f.first_start,
         MIN(t.state) AS state,
         l.gender
  FROM first_term f
  JOIN legislators_terms t
    ON t.id_bioguide = f.id_bioguide
   AND t.term_start = f.first_start
  JOIN legislators l
    ON l.id_bioguide = f.id_bioguide
  WHERE l.gender IN ('M', 'F')
  GROUP BY f.id_bioguide, f.first_start, l.gender
),
retained AS (
  SELECT c.state,
         c.gender,
         pr.p,
         COUNT(DISTINCT c.id_bioguide) AS n_retained
  FROM cohort c
  CROSS JOIN periods pr
  JOIN legislators_terms t
    ON t.id_bioguide = c.id_bioguide
   AND t.term_start <= (CAST(strftime('%Y', c.first_start) AS INTEGER) + pr.p) || '-12-31'
   AND t.term_end   >= (CAST(strftime('%Y', c.first_start) AS INTEGER) + pr.p) || '-12-31'
  GROUP BY c.state, c.gender, pr.p
)
SELECT state
FROM retained
WHERE n_retained > 0
GROUP BY state
HAVING COUNT(DISTINCT gender || '-' || p) = 12
ORDER BY state