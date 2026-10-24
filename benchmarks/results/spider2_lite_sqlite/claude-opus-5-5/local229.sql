WITH b AS (
  SELECT bb.match_id,
         bb.striker,
         MIN(bb.striker, bb.non_striker) AS pa,
         MAX(bb.striker, bb.non_striker) AS pb,
         COALESCE(bs.runs_scored, 0) AS r
  FROM ball_by_ball bb
  LEFT JOIN batsman_scored bs
    ON bs.match_id = bb.match_id
   AND bs.over_id = bb.over_id
   AND bs.ball_id = bb.ball_id
   AND bs.innings_no = bb.innings_no
),
p AS (
  SELECT match_id, pa, pb,
         SUM(CASE WHEN striker = pa THEN r ELSE 0 END) AS ra,
         SUM(CASE WHEN striker = pb THEN r ELSE 0 END) AS rb,
         SUM(r) AS total
  FROM b
  GROUP BY match_id, pa, pb
),
ranked AS (
  SELECT p.*, RANK() OVER (PARTITION BY match_id ORDER BY total DESC) AS rk
  FROM p
)
SELECT match_id,
       CASE WHEN ra > rb THEN pa ELSE pb END AS player1_id,
       CASE WHEN ra > rb THEN ra ELSE rb END AS player1_score,
       CASE WHEN ra > rb THEN pb ELSE pa END AS player2_id,
       CASE WHEN ra > rb THEN rb ELSE ra END AS player2_score,
       total AS partnership_score
FROM ranked
WHERE rk = 1
ORDER BY match_id