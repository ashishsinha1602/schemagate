WITH b AS (
  SELECT bb.match_id,
         MIN(bb.striker, bb.non_striker) AS a,
         MAX(bb.striker, bb.non_striker) AS c,
         bb.striker,
         COALESCE(bs.runs_scored, 0) AS runs
  FROM ball_by_ball bb
  LEFT JOIN batsman_scored bs
    ON bs.match_id = bb.match_id
   AND bs.over_id = bb.over_id
   AND bs.ball_id = bb.ball_id
   AND bs.innings_no = bb.innings_no
),
p AS (
  SELECT match_id, a, c,
         SUM(CASE WHEN striker = a THEN runs ELSE 0 END) AS sa,
         SUM(CASE WHEN striker = c THEN runs ELSE 0 END) AS sc,
         SUM(runs) AS total
  FROM b
  GROUP BY match_id, a, c
),
r AS (
  SELECT *, MAX(total) OVER (PARTITION BY match_id) AS mx
  FROM p
)
SELECT match_id,
       CASE WHEN sa > sc OR (sa = sc AND a > c) THEN a ELSE c END AS player_1_id,
       CASE WHEN sa > sc OR (sa = sc AND a > c) THEN sa ELSE sc END AS player_1_score,
       CASE WHEN sa > sc OR (sa = sc AND a > c) THEN c ELSE a END AS player_2_id,
       CASE WHEN sa > sc OR (sa = sc AND a > c) THEN sc ELSE sa END AS player_2_score,
       total AS partnership_runs
FROM r
WHERE total = mx
ORDER BY match_id