WITH MovieYears AS (
  SELECT
    MID,
    CAST(SUBSTR(year, -4) AS INTEGER) AS movie_year
  FROM main.Movie
), MovieActorGenders AS (
  SELECT
    MY.MID,
    MY.movie_year,
    P.Gender
  FROM MovieYears AS MY
  JOIN main.M_Cast AS MC
    ON MY.MID = MC.MID
  JOIN main.Person AS P
    ON MC.PID = P.PID
), MovieGenderSummary AS (
  SELECT
    MID,
    movie_year,
    SUM(CASE WHEN Gender = 'Male' THEN 1 ELSE 0 END) AS male_actor_count,
    COUNT(Gender) AS total_actor_count_in_cast
  FROM MovieActorGenders
  GROUP BY
    MID,
    movie_year
)
SELECT
  MY.movie_year AS year,
  COUNT(DISTINCT MY.MID) AS total_movies_in_year,
  CAST(SUM(CASE WHEN MGS.male_actor_count = 0 AND MGS.total_actor_count_in_cast > 0 THEN 1 ELSE 0 END) AS REAL) * 100.0 / COUNT(DISTINCT MY.MID) AS percentage_female_only
FROM MovieYears AS MY
LEFT JOIN MovieGenderSummary AS MGS
  ON MY.MID = MGS.MID
GROUP BY
  MY.movie_year
ORDER BY
  MY.movie_year