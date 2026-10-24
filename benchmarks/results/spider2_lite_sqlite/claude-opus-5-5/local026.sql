WITH ball_runs AS (
  SELECT b.match_id,
         b.innings_no,
         b.over_id,
         b.bowler,
         COALESCE(bs.runs_scored, 0) + COALESCE(er.extra_runs, 0) AS runs
  FROM ball_by_ball b
  LEFT JOIN batsman_scored bs
    ON bs.match_id = b.match_id
   AND bs.over_id = b.over_id
   AND bs.ball_id = b.ball_id
   AND bs.innings_no = b.innings_no
  LEFT JOIN extra_runs er
    ON er.match_id = b.match_id
   AND er.over_id = b.over_id
   AND er.ball_id = b.ball_id
   AND er.innings_no = b.innings_no
),
over_runs AS (
  SELECT match_id,
         innings_no,
         over_id,
         bowler,
         SUM(runs) AS runs
  FROM ball_runs
  GROUP BY match_id, innings_no, over_id, bowler
),
match_max AS (
  SELECT match_id,
         innings_no,
         over_id,
         bowler,
         runs,
         RANK() OVER (PARTITION BY match_id ORDER BY runs DESC) AS rk
  FROM over_runs
),
bowler_best AS (
  SELECT bowler,
         match_id,
         runs,
         ROW_NUMBER() OVER (PARTITION BY bowler ORDER BY runs DESC, match_id) AS rn
  FROM match_max
  WHERE rk = 1
)
SELECT bowler,
       match_id,
       runs AS max_runs_in_over
FROM bowler_best
WHERE rn = 1
ORDER BY runs DESC
LIMIT 3