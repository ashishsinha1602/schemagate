SELECT DISTINCT p.player_name
FROM (
  SELECT b.match_id, b.striker, SUM(bs.runs_scored) AS runs
  FROM ball_by_ball b
  JOIN batsman_scored bs
    ON bs.match_id = b.match_id
   AND bs.over_id = b.over_id
   AND bs.ball_id = b.ball_id
   AND bs.innings_no = b.innings_no
  GROUP BY b.match_id, b.striker
  HAVING SUM(bs.runs_scored) >= 100
) r
JOIN match m ON m.match_id = r.match_id
JOIN player_match pm ON pm.match_id = r.match_id AND pm.player_id = r.striker
JOIN player p ON p.player_id = r.striker
WHERE m.match_winner IS NOT NULL
  AND pm.team_id <> m.match_winner