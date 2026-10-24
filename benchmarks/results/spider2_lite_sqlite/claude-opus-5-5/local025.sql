WITH over_runs AS (
  SELECT match_id, innings_no, over_id, SUM(COALESCE(r, 0)) AS total_runs
  FROM (
    SELECT match_id, innings_no, over_id, runs_scored AS r FROM batsman_scored
    UNION ALL
    SELECT match_id, innings_no, over_id, extra_runs AS r FROM extra_runs
  )
  GROUP BY match_id, innings_no, over_id
),
ranked AS (
  SELECT o.*, ROW_NUMBER() OVER (PARTITION BY o.match_id ORDER BY o.total_runs DESC, o.innings_no, o.over_id) AS rn
  FROM over_runs o
),
top_overs AS (
  SELECT t.match_id, t.innings_no, t.over_id, t.total_runs,
         (SELECT b.bowler FROM ball_by_ball b
          WHERE b.match_id = t.match_id AND b.innings_no = t.innings_no AND b.over_id = t.over_id
          LIMIT 1) AS bowler
  FROM ranked t
  WHERE t.rn = 1
)
SELECT AVG(total_runs) AS avg_highest_over_runs
FROM top_overs