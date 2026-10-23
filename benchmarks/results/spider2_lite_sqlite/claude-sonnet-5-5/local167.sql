WITH first_state AS (
  SELECT id_bioguide, state,
         ROW_NUMBER() OVER (PARTITION BY id_bioguide ORDER BY term_start) AS rn
  FROM legislators_terms
),
dec31 AS (
  SELECT DISTINCT id_bioguide
  FROM legislators_terms
  WHERE substr(term_start, 1, 4) || '-12-31' <= term_end
)
SELECT f.state, COUNT(DISTINCT l.id_bioguide) AS female_legislator_count
FROM legislators l
JOIN first_state f ON f.id_bioguide = l.id_bioguide AND f.rn = 1
JOIN dec31 d ON d.id_bioguide = l.id_bioguide
WHERE l.gender = 'F'
GROUP BY f.state
ORDER BY female_legislator_count DESC
LIMIT 1