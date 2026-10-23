WITH EligibleGames AS (
  SELECT
    BS.BowlerID,
    BS.MatchID,
    BS.GameNumber,
    BS.HandiCapScore,
    T.TourneyDate,
    T.TourneyLocation
  FROM main.Bowler_Scores AS BS
  JOIN main.Tourney_Matches AS TM
    ON BS.MatchID = TM.MatchID
  JOIN main.Tournaments AS T
    ON TM.TourneyID = T.TourneyID
  WHERE
    BS.WonGame = TRUE AND BS.HandiCapScore <= 190 AND T.TourneyLocation IN ('Thunderbird Lanes', 'Totem Lanes', 'Bolero Lanes')
), QualifyingBowlers AS (
  SELECT
    BowlerID
  FROM EligibleGames
  GROUP BY
    BowlerID
  HAVING
    COUNT(DISTINCT TourneyLocation) = 3
)
SELECT
  B.BowlerID,
  B.BowlerFirstName,
  B.BowlerLastName,
  EG.MatchID,
  EG.GameNumber,
  EG.HandiCapScore,
  EG.TourneyDate,
  EG.TourneyLocation
FROM EligibleGames AS EG
JOIN QualifyingBowlers AS QB
  ON EG.BowlerID = QB.BowlerID
JOIN main.Bowlers AS B
  ON EG.BowlerID = B.BowlerID