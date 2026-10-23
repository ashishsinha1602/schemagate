WITH runs AS (
  SELECT b.bowler,
         SUM(COALESCE(bs.runs_scored, 0) + COALESCE(CASE WHEN er.extra_type IN ('wides', 'noballs') THEN er.extra_runs END, 0)) AS runs_conceded
  FROM ball_by_ball b
  LEFT JOIN batsman_scored bs
    ON bs.match_id = b.match_id AND bs.over_id = b.over_id AND bs.ball_id = b.ball_id AND bs.innings_no = b.innings_no
  LEFT JOIN extra_runs er
    ON er.match_id = b.match_id AND er.over_id = b.over_id AND er.ball_id = b.ball_id AND er.innings_no = b.innings_no
  GROUP BY b.bowler
),
wk AS (
  SELECT b.bowler, COUNT(*) AS wickets
  FROM wicket_taken w
  JOIN ball_by_ball b
    ON b.match_id = w.match_id AND b.over_id = w.over_id AND b.ball_id = w.ball_id AND b.innings_no = w.innings_no
  WHERE w.kind_out NOT IN ('run out', 'retired hurt', 'obstructing the field')
  GROUP BY b.bowler
)
SELECT p.player_name, r.runs_conceded * 1.0 / wk.wickets AS bowling_average
FROM runs r
JOIN wk ON wk.bowler = r.bowler
JOIN player p ON p.player_id = r.bowler
ORDER BY bowling_average ASC
LIMIT 1