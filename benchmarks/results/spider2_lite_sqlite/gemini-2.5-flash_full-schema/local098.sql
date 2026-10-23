WITH ActorYears AS (
  SELECT
    T1.PID,
    CAST(T2.year AS INTEGER) AS movie_year
  FROM main.M_Cast AS T1
  INNER JOIN main.Movie AS T2
    ON T1.MID = T2.MID
  GROUP BY
    T1.PID,
    CAST(T2.year AS INTEGER)
), ActorGaps AS (
  SELECT
    PID,
    movie_year,
    LAG(movie_year, 1, movie_year) OVER (PARTITION BY PID ORDER BY movie_year) AS prev_movie_year
  FROM ActorYears
), ActorsWithLargeGaps AS (
  SELECT DISTINCT
    PID
  FROM ActorGaps
  WHERE
    movie_year - prev_movie_year >= 4
)
SELECT
  COUNT(DISTINCT T1.PID)
FROM ActorYears AS T1
WHERE
  T1.PID NOT IN (
    SELECT
      PID
    FROM ActorsWithLargeGaps
  )