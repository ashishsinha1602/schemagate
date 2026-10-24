WITH first_state AS (
  SELECT id_bioguide, state
  FROM (
    SELECT t.id_bioguide, t.state,
           ROW_NUMBER() OVER (PARTITION BY t.id_bioguide ORDER BY t.term_start, t.term_number) AS rn
    FROM legislators_terms t
  )
  WHERE rn = 1
),
dec31 AS (
  SELECT DISTINCT id_bioguide
  FROM legislators_terms
  WHERE term_end >= substr(term_start, 1, 4) || '-12-31'
)
SELECT fs.state, COUNT(DISTINCT l.id_bioguide) AS female_legislator_count
FROM legislators l
JOIN first_state fs ON fs.id_bioguide = l.id_bioguide
JOIN dec31 d ON d.id_bioguide = l.id_bioguide
WHERE l.gender = 'F'
GROUP BY fs.state
ORDER BY female_legislator_count DESC
LIMIT 1