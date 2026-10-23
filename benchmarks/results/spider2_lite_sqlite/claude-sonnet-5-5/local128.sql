WITH wins AS (
  SELECT b.BowlerID, b.BowlerFirstName, b.BowlerLastName, bs.MatchID, bs.GameNumber, bs.HandiCapScore, t.TourneyDate, t.TourneyLocation
  FROM Bowlers b
  JOIN Bowler_Scores bs ON bs.BowlerID = b.BowlerID
  JOIN Tourney_Matches tm ON tm.MatchID = bs.MatchID
  JOIN Tournaments t ON t.TourneyID = tm.TourneyID
  WHERE bs.WonGame = 1
    AND bs.HandiCapScore <= 190
    AND t.TourneyLocation IN ('Thunderbird Lanes', 'Totem Lanes', 'Bolero Lanes')
)
SELECT BowlerID, BowlerFirstName, BowlerLastName, MatchID, GameNumber, HandiCapScore, TourneyDate, TourneyLocation
FROM wins
WHERE BowlerID IN (
  SELECT BowlerID FROM wins GROUP BY BowlerID HAVING COUNT(DISTINCT TourneyLocation) = 3
)
ORDER BY BowlerID, TourneyDate, MatchID, GameNumber