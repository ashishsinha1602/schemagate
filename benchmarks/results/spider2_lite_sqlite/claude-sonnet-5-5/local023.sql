WITH runs AS (
  SELECT bb.striker AS player_id, SUM(bs.runs_scored) AS total_runs
  FROM ball_by_ball bb
  JOIN batsman_scored bs ON bs.match_id = bb.match_id AND bs.over_id = bb.over_id AND bs.ball_id = bb.ball_id AND bs.innings_no = bb.innings_no
  JOIN match m ON m.match_id = bb.match_id
  WHERE m.season_id = 5
  GROUP BY bb.striker
),
matches_played AS (
  SELECT pm.player_id, COUNT(DISTINCT pm.match_id) AS matches
  FROM player_match pm
  JOIN match m ON m.match_id = pm.match_id
  WHERE m.season_id = 5
  GROUP BY pm.player_id
),
outs AS (
  SELECT w.player_out AS player_id, COUNT(*) AS dismissals
  FROM wicket_taken w
  JOIN match m ON m.match_id = w.match_id
  WHERE m.season_id = 5
  GROUP BY w.player_out
)
SELECT p.player_name,
       r.total_runs * 1.0 / mp.matches AS avg_runs_per_match,
       r.total_runs * 1.0 / NULLIF(o.dismissals, 0) AS batting_average
FROM runs r
JOIN matches_played mp ON mp.player_id = r.player_id
JOIN player p ON p.player_id = r.player_id
LEFT JOIN outs o ON o.player_id = r.player_id
ORDER BY avg_runs_per_match DESC
LIMIT 5