WITH role_counts AS (
  SELECT player_id, role, COUNT(*) AS cnt,
         ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY COUNT(*) DESC, role) AS rn
  FROM player_match
  GROUP BY player_id, role
),
matches_played AS (
  SELECT player_id, COUNT(DISTINCT match_id) AS matches
  FROM player_match
  GROUP BY player_id
),
bat_match AS (
  SELECT b.striker AS player_id, b.match_id,
         SUM(COALESCE(s.runs_scored, 0)) AS runs,
         COUNT(*) AS balls
  FROM ball_by_ball b
  LEFT JOIN batsman_scored s
    ON s.match_id = b.match_id AND s.over_id = b.over_id
   AND s.ball_id = b.ball_id AND s.innings_no = b.innings_no
  GROUP BY b.striker, b.match_id
),
batting AS (
  SELECT player_id,
         SUM(runs) AS total_runs,
         SUM(balls) AS balls_faced,
         MAX(runs) AS highest_score,
         SUM(CASE WHEN runs >= 30 THEN 1 ELSE 0 END) AS matches_30,
         SUM(CASE WHEN runs >= 50 THEN 1 ELSE 0 END) AS matches_50,
         SUM(CASE WHEN runs >= 100 THEN 1 ELSE 0 END) AS matches_100
  FROM bat_match
  GROUP BY player_id
),
dismissals AS (
  SELECT player_out AS player_id, COUNT(*) AS dismissals
  FROM wicket_taken
  WHERE player_out IS NOT NULL
  GROUP BY player_out
),
bowl_match AS (
  SELECT b.bowler AS player_id, b.match_id,
         COUNT(*) AS balls,
         SUM(COALESCE(s.runs_scored, 0)) AS runs,
         SUM(CASE WHEN w.player_out IS NOT NULL
                   AND w.kind_out NOT IN ('run out', 'retired hurt', 'obstructing the field')
                  THEN 1 ELSE 0 END) AS wickets
  FROM ball_by_ball b
  LEFT JOIN batsman_scored s
    ON s.match_id = b.match_id AND s.over_id = b.over_id
   AND s.ball_id = b.ball_id AND s.innings_no = b.innings_no
  LEFT JOIN wicket_taken w
    ON w.match_id = b.match_id AND w.over_id = b.over_id
   AND w.ball_id = b.ball_id AND w.innings_no = b.innings_no
  GROUP BY b.bowler, b.match_id
),
bowling AS (
  SELECT player_id, SUM(wickets) AS total_wickets,
         SUM(runs) AS runs_conceded, SUM(balls) AS balls_bowled
  FROM bowl_match
  GROUP BY player_id
),
best_bowl AS (
  SELECT player_id, wickets || '-' || runs AS best_bowling,
         ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY wickets DESC, runs ASC) AS rn
  FROM bowl_match
)
SELECT p.player_id,
       p.player_name,
       rc.role AS most_frequent_role,
       p.batting_hand,
       p.bowling_skill,
       COALESCE(bt.total_runs, 0) AS total_runs,
       COALESCE(mp.matches, 0) AS total_matches,
       COALESCE(d.dismissals, 0) AS total_dismissals,
       1.0 * bt.total_runs / NULLIF(d.dismissals, 0) AS batting_average,
       bt.highest_score,
       COALESCE(bt.matches_30, 0) AS matches_30_plus,
       COALESCE(bt.matches_50, 0) AS matches_50_plus,
       COALESCE(bt.matches_100, 0) AS matches_100_plus,
       COALESCE(bt.balls_faced, 0) AS total_balls_faced,
       100.0 * bt.total_runs / NULLIF(bt.balls_faced, 0) AS strike_rate,
       COALESCE(bw.total_wickets, 0) AS total_wickets,
       6.0 * bw.runs_conceded / NULLIF(bw.balls_bowled, 0) AS economy_rate,
       bb.best_bowling
FROM player p
LEFT JOIN role_counts rc ON rc.player_id = p.player_id AND rc.rn = 1
LEFT JOIN matches_played mp ON mp.player_id = p.player_id
LEFT JOIN batting bt ON bt.player_id = p.player_id
LEFT JOIN dismissals d ON d.player_id = p.player_id
LEFT JOIN bowling bw ON bw.player_id = p.player_id
LEFT JOIN best_bowl bb ON bb.player_id = p.player_id AND bb.rn = 1
ORDER BY p.player_id