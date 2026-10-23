WITH balls AS (
  SELECT match_id, over_id, ball_id, innings_no, runs_scored AS runs FROM batsman_scored
  UNION ALL
  SELECT match_id, over_id, ball_id, innings_no, extra_runs AS runs FROM extra_runs
),
over_tot AS (
  SELECT match_id, innings_no, over_id, SUM(runs) AS total_runs
  FROM balls
  GROUP BY match_id, innings_no, over_id
),
ranked AS (
  SELECT match_id, innings_no, over_id, total_runs,
         ROW_NUMBER() OVER (PARTITION BY match_id ORDER BY total_runs DESC, innings_no, over_id) AS rn
  FROM over_tot
),
best AS (
  SELECT match_id, innings_no, over_id, total_runs FROM ranked WHERE rn = 1
)
SELECT b.match_id,
       b.innings_no,
       b.over_id,
       b.total_runs,
       (SELECT MIN(bb.bowler) FROM ball_by_ball bb
        WHERE bb.match_id = b.match_id AND bb.innings_no = b.innings_no AND bb.over_id = b.over_id) AS bowler,
       AVG(b.total_runs) OVER () AS avg_highest_over_total
FROM best b
ORDER BY b.match_id