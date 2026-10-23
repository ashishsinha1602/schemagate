WITH FemaleLegislators AS (
  SELECT
    l.id_bioguide,
    lt.term_start,
    lt.term_end,
    lt.state
  FROM main.legislators AS l
  JOIN main.legislators_terms AS lt
    ON l.id_bioguide = lt.id_bioguide
  WHERE
    l.gender = 'F'
), FirstStatePerLegislator AS (
  SELECT
    id_bioguide,
    state,
    ROW_NUMBER() OVER (PARTITION BY id_bioguide ORDER BY term_start) AS rn
  FROM FemaleLegislators
), LegislatorsWithDec31Term AS (
  SELECT DISTINCT
    id_bioguide
  FROM FemaleLegislators
  WHERE
    term_end >= SUBSTR(term_start, 1, 4) || '-12-31'
)
SELECT
  fs.state,
  COUNT(DISTINCT fs.id_bioguide) AS legislator_count
FROM FirstStatePerLegislator AS fs
JOIN LegislatorsWithDec31Term AS ldt
  ON fs.id_bioguide = ldt.id_bioguide
WHERE
  fs.rn = 1
GROUP BY
  fs.state
ORDER BY
  legislator_count DESC
LIMIT 1