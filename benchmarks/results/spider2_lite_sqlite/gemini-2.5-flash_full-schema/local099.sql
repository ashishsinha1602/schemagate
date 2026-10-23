WITH YashChopraPID AS (
  SELECT
    PID
  FROM main.Person
  WHERE
    Name = 'Yash Chopra'
), ActorDirectorFilms AS (
  SELECT
    MC.PID AS ActorPID,
    MD.PID AS DirectorPID,
    COUNT(DISTINCT MC.MID) AS FilmCount
  FROM main.M_Cast AS MC
  JOIN main.M_Director AS MD
    ON MC.MID = MD.MID
  GROUP BY
    MC.PID,
    MD.PID
), ActorFilmStats AS (
  SELECT
    ADF.ActorPID,
    SUM(CASE WHEN ADF.DirectorPID = (
      SELECT
        PID
      FROM YashChopraPID
    ) THEN ADF.FilmCount ELSE 0 END) AS FilmsWithYashChopra,
    MAX(CASE WHEN ADF.DirectorPID != (
      SELECT
        PID
      FROM YashChopraPID
    ) THEN ADF.FilmCount ELSE 0 END) AS MaxFilmsWithOtherDirectors
  FROM ActorDirectorFilms AS ADF
  GROUP BY
    ADF.ActorPID
)
SELECT
  COUNT(ActorPID)
FROM ActorFilmStats
WHERE
  FilmsWithYashChopra > MaxFilmsWithOtherDirectors