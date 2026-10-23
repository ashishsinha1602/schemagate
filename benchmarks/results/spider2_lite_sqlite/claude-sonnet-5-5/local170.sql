WITH first_terms AS (
  SELECT id_bioguide, MIN(term_start) AS first_start
  FROM legislators_terms
  GROUP BY id_bioguide
),
first_state AS (
  SELECT ft.id_bioguide, ft.first_start, MIN(lt.state) AS state
  FROM first_terms ft
  JOIN legislators_terms lt ON lt.id_bioguide = ft.id_bioguide AND lt.term_start = ft.first_start
  GROUP BY ft.id_bioguide, ft.first_start
),
offsets(n) AS (
  VALUES (0),(2),(4),(6),(8),(10)
),
targets AS (
  SELECT fs.id_bioguide, fs.state, l.gender, o.n,
         (CAST(substr(fs.first_start, 1, 4) AS INTEGER) + o.n) || '-12-31' AS target_date
  FROM first_state fs
  JOIN legislators l ON l.id_bioguide = fs.id_bioguide
  CROSS JOIN offsets o
  WHERE l.gender IN ('M','F')
),
retained AS (
  SELECT DISTINCT t.state, t.gender, t.n, t.id_bioguide
  FROM targets t
  JOIN legislators_terms lt
    ON lt.id_bioguide = t.id_bioguide
   AND lt.term_start <= t.target_date
   AND lt.term_end >= t.target_date
)
SELECT state
FROM (
  SELECT state, gender, n
  FROM retained
  GROUP BY state, gender, n
)
GROUP BY state
HAVING COUNT(*) = 12