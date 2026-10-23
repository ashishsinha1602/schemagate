WITH player_runs AS (
  SELECT b.match_id, b.striker AS player_id, SUM(bs.runs_scored) AS runs
  FROM ball_by_ball b
  JOIN batsman_scored bs
    ON bs.match_id = b.match_id AND bs.over_id = b.over_id AND bs.ball_id = b.ball_id AND bs.innings_no = b.innings_no
  GROUP BY b.match_id, b.striker
),
player_avg AS (
  SELECT pm.player_id,
         SUM(COALESCE(pr.runs, 0)) * 1.0 / COUNT(DISTINCT pm.match_id) AS avg_runs
  FROM player_match pm
  LEFT JOIN player_runs pr ON pr.match_id = pm.match_id AND pr.player_id = pm.player_id
  GROUP BY pm.player_id
)
SELECT p.country_name, AVG(pa.avg_runs) AS country_batting_average
FROM player_avg pa
JOIN player p ON p.player_id = pa.player_id
GROUP BY p.country_name
ORDER BY country_batting_average DESC
LIMIT 5