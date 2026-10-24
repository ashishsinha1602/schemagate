WITH qualifying AS (
  SELECT bs.BowlerID, bs.MatchID, bs.GameNumber, bs.HandiCapScore, t.TourneyDate, t.TourneyLocation
  FROM Bowler_Scores bs
  JOIN Tourney_Matches tm ON tm.MatchID = bs.MatchID
  JOIN Tournaments t ON t.TourneyID = tm.TourneyID
  WHERE bs.WonGame = 1
    AND bs.HandiCapScore <= 190
    AND t.TourneyLocation IN ('Thunderbird Lanes', 'Totem Lanes', 'Bolero Lanes')
),
eligible AS (
  SELECT BowlerID
  FROM qualifying
  GROUP BY BowlerID
  HAVING COUNT(DISTINCT TourneyLocation) = 3
)
SELECT b.BowlerID, b.BowlerFirstName, b.BowlerLastName, q.MatchID, q.GameNumber, q.HandiCapScore, q.TourneyDate, q.TourneyLocation
FROM qualifying q
JOIN eligible e ON e.BowlerID = q.BowlerID
JOIN Bowlers b ON b.BowlerID = q.BowlerID
ORDER BY b.BowlerID, q.MatchID, q.GameNumber