WITH per_match AS (
  SELECT b.striker, bs.match_id, SUM(bs.runs_scored) AS runs
  FROM batsman_scored bs
  JOIN ball_by_ball b ON b.match_id = bs.match_id AND b.over_id = bs.over_id AND b.ball_id = bs.ball_id AND b.innings_no = bs.innings_no
  GROUP BY b.striker, bs.match_id
),
totals AS (
  SELECT striker, SUM(runs) AS total_runs, MAX(runs) AS max_runs
  FROM per_match
  GROUP BY striker
)
SELECT AVG(total_runs) AS avg_total_runs
FROM totals
WHERE max_runs > 50