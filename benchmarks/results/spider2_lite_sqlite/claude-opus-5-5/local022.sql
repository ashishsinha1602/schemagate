SELECT DISTINCT p.player_name
FROM (
  SELECT bb.match_id, bb.striker AS player_id, SUM(bs.runs_scored) AS total_runs
  FROM ball_by_ball bb
  JOIN batsman_scored bs
    ON bs.match_id = bb.match_id
   AND bs.over_id = bb.over_id
   AND bs.ball_id = bb.ball_id
   AND bs.innings_no = bb.innings_no
  GROUP BY bb.match_id, bb.striker
) r
JOIN player_match pm
  ON pm.match_id = r.match_id
 AND pm.player_id = r.player_id
JOIN match m
  ON m.match_id = r.match_id
JOIN player p
  ON p.player_id = r.player_id
WHERE r.total_runs >= 100
  AND m.match_winner IS NOT NULL
  AND pm.team_id <> m.match_winner