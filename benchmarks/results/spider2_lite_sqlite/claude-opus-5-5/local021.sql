WITH striker_match AS (
  SELECT b.striker, b.match_id, SUM(s.runs_scored) AS match_runs
  FROM ball_by_ball b
  JOIN batsman_scored s
    ON s.match_id = b.match_id
   AND s.over_id = b.over_id
   AND s.ball_id = b.ball_id
   AND s.innings_no = b.innings_no
  GROUP BY b.striker, b.match_id
),
qualified AS (
  SELECT striker, SUM(match_runs) AS total_runs
  FROM striker_match
  GROUP BY striker
  HAVING MAX(match_runs) > 50
)
SELECT AVG(total_runs) AS avg_total_runs
FROM qualified