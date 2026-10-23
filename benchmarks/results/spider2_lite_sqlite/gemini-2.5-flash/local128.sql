WITH QualifiedGames AS (
  SELECT
    BS.BowlerID,
    BS.MatchID,
    BS.GameNumber,
    BS.HandiCapScore,
    T.TourneyLocation,
    T.TourneyDate
  FROM main.Bowler_Scores AS BS
  JOIN main.Tourney_Matches AS TM
    ON BS.MatchID = TM.MatchID
  JOIN main.Tournaments AS T
    ON TM.TourneyID = T.TourneyID
  WHERE
    BS.WonGame = 1 AND BS.HandiCapScore <= 190 AND T.TourneyLocation IN ('Thunderbird Lanes', 'Totem Lanes', 'Bolero Lanes')
), BowlersAtAllVenues AS (
  SELECT
    BowlerID
  FROM QualifiedGames
  GROUP BY
    BowlerID
  HAVING
    COUNT(DISTINCT TourneyLocation) = 3
)
SELECT
  B.BowlerID,
  B.BowlerFirstName,
  B.BowlerLastName,
  QG.MatchID,
  QG.GameNumber,
  QG.HandiCapScore,
  QG.TourneyDate,
  QG.TourneyLocation
FROM main.Bowlers AS B
JOIN QualifiedGames AS QG
  ON B.BowlerID = QG.BowlerID
JOIN BowlersAtAllVenues AS BAV
  ON B.BowlerID = BAV.BowlerID