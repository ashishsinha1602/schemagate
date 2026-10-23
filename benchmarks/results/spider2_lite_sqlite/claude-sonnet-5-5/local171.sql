WITH la AS (
  SELECT t.id_bioguide, t.term_start, t.term_end
  FROM legislators_terms t
  JOIN legislators l ON l.id_bioguide = t.id_bioguide
  WHERE l.gender = 'M' AND t.state = 'LA'
),
firsts AS (
  SELECT id_bioguide, MIN(term_start) AS fs
  FROM la
  GROUP BY id_bioguide
),
n(k) AS (
  SELECT 31
  UNION ALL
  SELECT k + 1 FROM n WHERE k < 49
)
SELECT n.k AS years_elapsed, COUNT(DISTINCT f.id_bioguide) AS legislators_count
FROM firsts f
CROSS JOIN n
JOIN la ON la.id_bioguide = f.id_bioguide
  AND la.term_start <= (CAST(strftime('%Y', f.fs) AS INTEGER) + n.k) || '-12-31'
  AND la.term_end >= (CAST(strftime('%Y', f.fs) AS INTEGER) + n.k) || '-12-31'
GROUP BY n.k
ORDER BY n.k