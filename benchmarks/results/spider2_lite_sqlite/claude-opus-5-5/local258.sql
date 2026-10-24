WITH d AS (
  SELECT b.bowler,
         b.match_id,
         COALESCE(s.runs_scored, 0) AS runs,
         CASE WHEN w.kind_out IS NOT NULL
                   AND w.kind_out NOT IN ('run out', 'retired hurt', 'obstructing the field')
              THEN 1 ELSE 0 END AS wk
  FROM ball_by_ball b
  LEFT JOIN batsman_scored s
    ON s.match_id = b.match_id AND s.over_id = b.over_id
   AND s.ball_id = b.ball_id AND s.innings_no = b.innings_no
  LEFT JOIN wicket_taken w
    ON w.match_id = b.match_id AND w.over_id = b.over_id
   AND w.ball_id = b.ball_id AND w.innings_no = b.innings_no
),
m AS (
  SELECT bowler, match_id, SUM(wk) AS w, SUM(runs) AS r
  FROM d
  GROUP BY bowler, match_id
),
best AS (
  SELECT bowler,
         w || '-' || r AS best_bowling,
         ROW_NUMBER() OVER (PARTITION BY bowler ORDER BY w DESC, r ASC) AS rn
  FROM m
),
tot AS (
  SELECT bowler, SUM(wk) AS wickets, SUM(runs) AS runs, COUNT(*) AS balls
  FROM d
  GROUP BY bowler
)
SELECT t.bowler,
       p.player_name,
       t.wickets,
       ROUND(t.runs * 6.0 / t.balls, 2) AS economy_rate,
       ROUND(t.balls * 1.0 / NULLIF(t.wickets, 0), 2) AS strike_rate,
       bb.best_bowling
FROM tot t
LEFT JOIN player p ON p.player_id = t.bowler
LEFT JOIN best bb ON bb.bowler = t.bowler AND bb.rn = 1
ORDER BY t.wickets DESC