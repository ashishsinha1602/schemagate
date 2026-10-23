WITH ball AS (
  SELECT b.bowler, b.match_id,
         COALESCE(s.runs_scored, 0) AS runs,
         CASE WHEN e.extra_type IN ('wides', 'noballs') THEN 0 ELSE 1 END AS legal,
         CASE WHEN w.kind_out IS NOT NULL AND w.kind_out NOT IN ('run out', 'retired hurt', 'obstructing the field') THEN 1 ELSE 0 END AS wk
  FROM ball_by_ball b
  LEFT JOIN batsman_scored s ON s.match_id = b.match_id AND s.over_id = b.over_id AND s.ball_id = b.ball_id AND s.innings_no = b.innings_no
  LEFT JOIN extra_runs e ON e.match_id = b.match_id AND e.over_id = b.over_id AND e.ball_id = b.ball_id AND e.innings_no = b.innings_no
  LEFT JOIN wicket_taken w ON w.match_id = b.match_id AND w.over_id = b.over_id AND w.ball_id = b.ball_id AND w.innings_no = b.innings_no
),
per_match AS (
  SELECT bowler, match_id, SUM(wk) AS wickets, SUM(runs) AS runs, SUM(legal) AS balls
  FROM ball
  GROUP BY bowler, match_id
),
ranked AS (
  SELECT bowler, wickets, runs,
         ROW_NUMBER() OVER (PARTITION BY bowler ORDER BY wickets DESC, runs ASC, match_id) AS rn
  FROM per_match
),
tot AS (
  SELECT bowler, SUM(wickets) AS total_wickets, SUM(runs) AS total_runs, SUM(balls) AS total_balls
  FROM per_match
  GROUP BY bowler
)
SELECT t.bowler AS player_id,
       p.player_name,
       t.total_wickets,
       CASE WHEN t.total_balls > 0 THEN t.total_runs * 6.0 / t.total_balls END AS economy_rate,
       CASE WHEN t.total_wickets > 0 THEN t.total_balls * 1.0 / t.total_wickets END AS strike_rate,
       r.wickets || '-' || r.runs AS best_bowling
FROM tot t
JOIN ranked r ON r.bowler = t.bowler AND r.rn = 1
LEFT JOIN player p ON p.player_id = t.bowler
ORDER BY t.total_wickets DESC, p.player_name