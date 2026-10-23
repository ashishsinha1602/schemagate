WITH ActorMovieYears AS (
  SELECT DISTINCT
    T1.PID,
    CAST(T2.year AS INTEGER) AS movie_year
  FROM main.M_Cast AS T1
  JOIN main.Movie AS T2
    ON T1.MID = T2.MID
), ActorYearGaps AS (
  SELECT
    PID,
    movie_year,
    LAG(movie_year, 1, movie_year) OVER (PARTITION BY PID ORDER BY movie_year) AS prev_movie_year
  FROM ActorMovieYears
), ActorsWithLongGaps AS (
  SELECT DISTINCT
    PID
  FROM ActorYearGaps
  WHERE
    (movie_year - prev_movie_year) > 3
)
SELECT
  COUNT(DISTINCT T1.PID)
FROM main.M_Cast AS T1
WHERE
  T1.PID NOT IN (
    SELECT
      PID
    FROM ActorsWithLongGaps
  )