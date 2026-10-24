WITH nf_person AS (
  SELECT TRIM(PID) AS PID
  FROM Person
  WHERE Gender IS NULL OR Gender <> 'Female'
),
nf_movie AS (
  SELECT DISTINCT TRIM(MID) AS MID
  FROM M_Cast
  WHERE TRIM(PID) IN (SELECT PID FROM nf_person)
),
m AS (
  SELECT DISTINCT TRIM(MID) AS MID, CAST(SUBSTR(year, -4) AS INTEGER) AS yr
  FROM Movie
),
flagged AS (
  SELECT yr, MID,
         CASE WHEN MID IN (SELECT MID FROM nf_movie) THEN 0 ELSE 1 END AS is_female_only
  FROM m
)
SELECT
  yr AS year,
  COUNT(*) AS total_movies,
  SUM(is_female_only) * 100.0 / COUNT(*) AS pct_exclusively_female
FROM flagged
GROUP BY yr
ORDER BY yr