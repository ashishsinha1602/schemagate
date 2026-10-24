WITH runs AS (
  SELECT b.bowler,
         SUM(COALESCE(bs.runs_scored, 0)
             + CASE WHEN er.extra_type IN ('wides', 'noballs') THEN COALESCE(er.extra_runs, 0) ELSE 0 END) AS runs_conceded
  FROM ball_by_ball b
  LEFT JOIN batsman_scored bs
    ON bs.match_id = b.match_id AND bs.over_id = b.over_id
   AND bs.ball_id = b.ball_id AND bs.innings_no = b.innings_no
  LEFT JOIN extra_runs er
    ON er.match_id = b.match_id AND er.over_id = b.over_id
   AND er.ball_id = b.ball_id AND er.innings_no = b.innings_no
  GROUP BY b.bowler
),
wkts AS (
  SELECT b.bowler, COUNT(*) AS wickets
  FROM ball_by_ball b
  JOIN wicket_taken w
    ON w.match_id = b.match_id AND w.over_id = b.over_id
   AND w.ball_id = b.ball_id AND w.innings_no = b.innings_no
  WHERE w.kind_out NOT IN ('run out', 'retired hurt', 'obstructing the field')
  GROUP BY b.bowler
)
SELECT p.player_id, p.player_name,
       CAST(r.runs_conceded AS REAL) / w.wickets AS bowling_average
FROM runs r
JOIN wkts w ON w.bowler = r.bowler
JOIN player p ON p.player_id = r.bowler
WHERE w.wickets > 0
ORDER BY bowling_average ASC
LIMIT 1