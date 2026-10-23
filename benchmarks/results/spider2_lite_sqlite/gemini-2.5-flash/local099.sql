WITH YashChopra AS (
  SELECT
    PID
  FROM main.Person
  WHERE
    Name = 'Yash Chopra'
), ActorDirectorFilms AS (
  SELECT
    MC.PID AS ActorPID,
    MD.PID AS DirectorPID,
    MC.MID
  FROM main.M_Cast AS MC
  JOIN main.M_Director AS MD
    ON MC.MID = MD.MID
), ActorDirectorCounts AS (
  SELECT
    ActorPID,
    DirectorPID,
    COUNT(DISTINCT MID) AS FilmCount
  FROM ActorDirectorFilms
  GROUP BY
    ActorPID,
    DirectorPID
), ActorYashChopraCounts AS (
  SELECT
    ADC.ActorPID,
    ADC.FilmCount AS YashChopraFilmCount
  FROM ActorDirectorCounts AS ADC
  JOIN YashChopra AS YC
    ON ADC.DirectorPID = YC.PID
), ActorMaxOtherDirectorCounts AS (
  SELECT
    ADC.ActorPID,
    MAX(ADC.FilmCount) AS MaxOtherFilmCount
  FROM ActorDirectorCounts AS ADC
  JOIN YashChopra AS YC
    ON ADC.DirectorPID != YC.PID
  GROUP BY
    ADC.ActorPID
)
SELECT
  COUNT(DISTINCT AYC.ActorPID)
FROM ActorYashChopraCounts AS AYC
LEFT JOIN ActorMaxOtherDirectorCounts AS AMODC
  ON AYC.ActorPID = AMODC.ActorPID
WHERE
  AYC.YashChopraFilmCount > COALESCE(AMODC.MaxOtherFilmCount, 0)