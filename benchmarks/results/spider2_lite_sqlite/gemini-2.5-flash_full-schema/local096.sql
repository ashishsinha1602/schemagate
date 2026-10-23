WITH MovieYears AS (
  SELECT
    MID,
    CAST(SUBSTR(year, -4) AS INTEGER) AS movie_year
  FROM main.Movie
),
MoviesWithMaleActors AS (
  SELECT DISTINCT T1.MID
  FROM main.M_Cast AS T1
  JOIN main.Person AS T2
    ON T1.PID = T2.PID
  WHERE T2.Gender = 'Male'
),
MoviesWithFemaleActors AS (
  SELECT DISTINCT T1.MID
  FROM main.M_Cast AS T1
  JOIN main.Person AS T2
    ON T1.PID = T2.PID
  WHERE T2.Gender = 'Female'
),
MovieGenderStatus AS (
  SELECT
    MY.movie_year,
    MY.MID,
    CASE
      WHEN MY.MID IN (SELECT MID FROM MoviesWithFemaleActors)
       AND MY.MID NOT IN (SELECT MID FROM MoviesWithMaleActors) THEN 1
      ELSE 0
    END AS is_exclusively_female
  FROM MovieYears AS MY
)
SELECT
  MGS.movie_year,
  COUNT(MGS.MID) AS total_movies,
  CAST(SUM(MGS.is_exclusively_female) AS REAL) * 100.0 / COUNT(MGS.MID) AS percentage_exclusively_female
FROM MovieGenderStatus AS MGS
GROUP BY
  MGS.movie_year
ORDER BY
  MGS.movie_year