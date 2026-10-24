WITH RECURSIVE nums(n) AS (
  SELECT 31
  UNION ALL
  SELECT n + 1 FROM nums WHERE n < 49
),
first_terms AS (
  SELECT t.id_bioguide, MIN(t.term_start) AS first_term
  FROM legislators_terms t
  JOIN legislators l ON l.id_bioguide = t.id_bioguide
  WHERE l.gender = 'M'
  GROUP BY t.id_bioguide
),
checks AS (
  SELECT f.id_bioguide, nums.n,
         (CAST(strftime('%Y', f.first_term) AS INTEGER) + nums.n) || '-12-31' AS check_date
  FROM first_terms f
  CROSS JOIN nums
)
SELECT c.n AS years_since_first_term,
       COUNT(DISTINCT c.id_bioguide) AS legislator_count
FROM checks c
JOIN legislators_terms t
  ON t.id_bioguide = c.id_bioguide
 AND t.state = 'LA'
 AND t.term_start <= c.check_date
 AND t.term_end >= c.check_date
GROUP BY c.n
ORDER BY c.n