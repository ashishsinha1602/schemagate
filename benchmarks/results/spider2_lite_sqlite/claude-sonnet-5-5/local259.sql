WITH role_cnt AS (
  SELECT player_id, role, COUNT(*) AS c
  FROM player_match
  GROUP BY player_id, role
),
top_role AS (
  SELECT player_id, role,
         ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY c DESC, role) AS rn
  FROM role_cnt
),
matches_played AS (
  SELECT player_id, COUNT(DISTINCT match_id) AS matches
  FROM player_match
  GROUP BY player_id
),
bat_match AS (
  SELECT b.striker AS player_id, b.match_id,
         SUM(bs.runs_scored) AS runs, COUNT(*) AS balls
  FROM ball_by_ball b
  JOIN batsman_scored bs
    ON bs.match_id = b.match_id AND bs.over_id = b.over_id
   AND bs.ball_id = b.ball_id AND bs.innings_no = b.innings_no
  GROUP BY b.striker, b.match_id
),
bat_tot AS (
  SELECT player_id,
         SUM(runs) AS total_runs,
         SUM(balls) AS total_balls,
         MAX(runs) AS highest,
         SUM(CASE WHEN runs >= 30 THEN 1 ELSE 0 END) AS m30,
         SUM(CASE WHEN runs >= 50 THEN 1 ELSE 0 END) AS m50,
         SUM(CASE WHEN runs >= 100 THEN 1 ELSE 0 END) AS m100
  FROM bat_match
  GROUP BY player_id
),
dism AS (
  SELECT player_out AS player_id, COUNT(*) AS dismissals
  FROM wicket_taken
  GROUP BY player_out
),
bowl_runs AS (
  SELECT b.bowler, b.match_id,
         SUM(bs.runs_scored) AS runs, COUNT(*) AS balls
  FROM ball_by_ball b
  JOIN batsman_scored bs
    ON bs.match_id = b.match_id AND bs.over_id = b.over_id
   AND bs.ball_id = b.ball_id AND bs.innings_no = b.innings_no
  GROUP BY b.bowler, b.match_id
),
wk AS (
  SELECT b.bowler, b.match_id, COUNT(*) AS wkts
  FROM wicket_taken w
  JOIN ball_by_ball b
    ON w.match_id = b.match_id AND w.over_id = b.over_id
   AND w.ball_id = b.ball_id AND w.innings_no = b.innings_no
  WHERE w.kind_out NOT IN ('run out', 'retired hurt', 'obstructing the field')
  GROUP BY b.bowler, b.match_id
),
bowl_match AS (
  SELECT r.bowler, r.match_id, r.runs, r.balls, COALESCE(k.wkts, 0) AS wkts
  FROM bowl_runs r
  LEFT JOIN wk k ON k.bowler = r.bowler AND k.match_id = r.match_id
),
bowl_tot AS (
  SELECT bowler, SUM(runs) AS runs, SUM(balls) AS balls
  FROM bowl_runs
  GROUP BY bowler
),
wk_tot AS (
  SELECT bowler, SUM(wkts) AS wkts
  FROM wk
  GROUP BY bowler
),
best AS (
  SELECT bowler, wkts, runs,
         ROW_NUMBER() OVER (PARTITION BY bowler ORDER BY wkts DESC, runs ASC) AS rn
  FROM bowl_match
)
SELECT p.player_id,
       p.player_name,
       tr.role AS most_frequent_role,
       p.batting_hand,
       p.bowling_skill,
       COALESCE(bt.total_runs, 0) AS total_runs,
       COALESCE(mp.matches, 0) AS total_matches,
       COALESCE(d.dismissals, 0) AS total_dismissals,
       CASE WHEN COALESCE(d.dismissals, 0) > 0 THEN COALESCE(bt.total_runs, 0) * 1.0 / d.dismissals END AS batting_average,
       COALESCE(bt.highest, 0) AS highest_score,
       COALESCE(bt.m30, 0) AS matches_30_plus,
       COALESCE(bt.m50, 0) AS matches_50_plus,
       COALESCE(bt.m100, 0) AS matches_100_plus,
       COALESCE(bt.total_balls, 0) AS total_balls_faced,
       CASE WHEN COALESCE(bt.total_balls, 0) > 0 THEN bt.total_runs * 100.0 / bt.total_balls END AS strike_rate,
       COALESCE(wt.wkts, 0) AS total_wickets,
       CASE WHEN COALESCE(bw.balls, 0) > 0 THEN bw.runs * 6.0 / bw.balls END AS economy_rate,
       CASE WHEN bs.bowler IS NOT NULL THEN bs.wkts || '-' || bs.runs END AS best_bowling
FROM player p
LEFT JOIN top_role tr ON tr.player_id = p.player_id AND tr.rn = 1
LEFT JOIN matches_played mp ON mp.player_id = p.player_id
LEFT JOIN bat_tot bt ON bt.player_id = p.player_id
LEFT JOIN dism d ON d.player_id = p.player_id
LEFT JOIN bowl_tot bw ON bw.bowler = p.player_id
LEFT JOIN wk_tot wt ON wt.bowler = p.player_id
LEFT JOIN best bs ON bs.bowler = p.player_id AND bs.rn = 1
ORDER BY p.player_id