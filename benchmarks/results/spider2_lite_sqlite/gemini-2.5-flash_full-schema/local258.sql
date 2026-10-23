WITH bowler_deliveries_details AS (
  SELECT
    bb.match_id,
    bb.bowler,
    bs.runs_scored AS runs_conceded_off_bat,
    CASE
      WHEN wt.kind_out IS NOT NULL AND wt.kind_out NOT IN ('run out', 'obstructing the field') THEN 1
      ELSE 0
    END AS is_wicket_taken_by_bowler
  FROM main.ball_by_ball AS bb
  JOIN main.batsman_scored AS bs
    ON bb.match_id = bs.match_id
    AND bb.over_id = bs.over_id
    AND bb.ball_id = bs.ball_id
    AND bb.innings_no = bs.innings_no
  LEFT JOIN main.wicket_taken AS wt
    ON bb.match_id = wt.match_id
    AND bb.over_id = wt.over_id
    AND bb.ball_id = wt.ball_id
    AND bb.innings_no = wt.innings_no
), bowler_overall_stats AS (
  SELECT
    bowler,
    SUM(runs_conceded_off_bat) AS total_runs_conceded,
    COUNT(*) AS total_balls_bowled,
    SUM(is_wicket_taken_by_bowler) AS total_wickets
  FROM bowler_deliveries_details
  GROUP BY
    bowler
), bowler_match_performance AS (
  SELECT
    match_id,
    bowler,
    SUM(runs_conceded_off_bat) AS match_runs_conceded,
    SUM(is_wicket_taken_by_bowler) AS match_wickets
  FROM bowler_deliveries_details
  GROUP BY
    match_id,
    bowler
), best_bowling_performance AS (
  SELECT
    bowler,
    match_wickets,
    match_runs_conceded,
    RANK() OVER (PARTITION BY bowler ORDER BY match_wickets DESC, match_runs_conceded ASC) AS rn
  FROM bowler_match_performance
)
SELECT
  p.player_name,
  bos.total_wickets,
  CASE
    WHEN bos.total_balls_bowled = 0 THEN 0.0
    ELSE (bos.total_runs_conceded * 6.0) / bos.total_balls_bowled
  END AS economy_rate,
  CASE
    WHEN bos.total_wickets = 0 THEN NULL
    ELSE bos.total_balls_bowled * 1.0 / bos.total_wickets
  END AS strike_rate,
  printf('%d-%d', bbp.match_wickets, bbp.match_runs_conceded) AS best_bowling_performance
FROM bowler_overall_stats AS bos
JOIN main.player AS p
  ON bos.bowler = p.player_id
LEFT JOIN best_bowling_performance AS bbp
  ON bos.bowler = bbp.bowler
  AND bbp.rn = 1
ORDER BY
  p.player_name