WITH s5 AS (
  SELECT match_id FROM match WHERE season_id = 5
),
match_runs AS (
  SELECT b.striker AS player_id, b.match_id, SUM(COALESCE(bs.runs_scored, 0)) AS runs
  FROM ball_by_ball b
  JOIN s5 ON s5.match_id = b.match_id
  LEFT JOIN batsman_scored bs
    ON bs.match_id = b.match_id AND bs.over_id = b.over_id
   AND bs.ball_id = b.ball_id AND bs.innings_no = b.innings_no
  GROUP BY b.striker, b.match_id
),
per_player AS (
  SELECT player_id, SUM(runs) AS total_runs, COUNT(*) AS matches,
         SUM(runs) * 1.0 / COUNT(*) AS avg_runs_per_match
  FROM match_runs
  GROUP BY player_id
),
dismissals AS (
  SELECT w.player_out AS player_id, COUNT(*) AS outs
  FROM wicket_taken w
  JOIN s5 ON s5.match_id = w.match_id
  GROUP BY w.player_out
)
SELECT p.player_name,
       pp.avg_runs_per_match,
       CASE WHEN COALESCE(d.outs, 0) = 0 THEN NULL
            ELSE pp.total_runs * 1.0 / d.outs END AS batting_average
FROM per_player pp
JOIN player p ON p.player_id = pp.player_id
LEFT JOIN dismissals d ON d.player_id = pp.player_id
ORDER BY pp.avg_runs_per_match DESC
LIMIT 5