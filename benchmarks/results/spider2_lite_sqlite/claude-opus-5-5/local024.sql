WITH match_runs AS (
  SELECT bb.striker AS player_id,
         bb.match_id,
         SUM(bs.runs_scored) AS runs
  FROM ball_by_ball bb
  JOIN batsman_scored bs
    ON bs.match_id = bb.match_id
   AND bs.over_id = bb.over_id
   AND bs.ball_id = bb.ball_id
   AND bs.innings_no = bb.innings_no
  GROUP BY bb.striker, bb.match_id
),
player_matches AS (
  SELECT pm.player_id,
         pm.match_id,
         COALESCE(mr.runs, 0) AS runs
  FROM player_match pm
  LEFT JOIN match_runs mr
    ON mr.player_id = pm.player_id
   AND mr.match_id = pm.match_id
),
player_avg AS (
  SELECT player_id,
         AVG(runs) AS avg_runs_per_match
  FROM player_matches
  GROUP BY player_id
)
SELECT p.country_name,
       AVG(pa.avg_runs_per_match) AS country_batting_average
FROM player_avg pa
JOIN player p ON p.player_id = pa.player_id
GROUP BY p.country_name
ORDER BY country_batting_average DESC
LIMIT 5