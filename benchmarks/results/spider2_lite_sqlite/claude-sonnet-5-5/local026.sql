WITH over_runs AS (
  SELECT b.match_id, b.innings_no, b.over_id, b.bowler,
         SUM(COALESCE(bs.runs_scored, 0) + COALESCE(er.extra_runs, 0)) AS runs
  FROM ball_by_ball b
  LEFT JOIN batsman_scored bs
    ON bs.match_id = b.match_id AND bs.over_id = b.over_id AND bs.ball_id = b.ball_id AND bs.innings_no = b.innings_no
  LEFT JOIN extra_runs er
    ON er.match_id = b.match_id AND er.over_id = b.over_id AND er.ball_id = b.ball_id AND er.innings_no = b.innings_no
  GROUP BY b.match_id, b.innings_no, b.over_id, b.bowler
),
ranked AS (
  SELECT *, RANK() OVER (PARTITION BY match_id ORDER BY runs DESC) AS rnk
  FROM over_runs
)
SELECT p.player_name, r.bowler AS player_id, r.match_id, r.innings_no, r.over_id, r.runs
FROM ranked r
JOIN player p ON p.player_id = r.bowler
WHERE r.rnk = 1
ORDER BY r.runs DESC
LIMIT 3