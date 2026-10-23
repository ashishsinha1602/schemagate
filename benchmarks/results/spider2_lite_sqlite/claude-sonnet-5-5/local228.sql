WITH bat AS (
  SELECT m.season_id, b.striker AS player_id, SUM(bs.runs_scored) AS total_runs,
         ROW_NUMBER() OVER (PARTITION BY m.season_id ORDER BY SUM(bs.runs_scored) DESC, b.striker ASC) AS rn
  FROM batsman_scored bs
  JOIN ball_by_ball b ON b.match_id = bs.match_id AND b.over_id = bs.over_id AND b.ball_id = bs.ball_id AND b.innings_no = bs.innings_no
  JOIN match m ON m.match_id = bs.match_id
  GROUP BY m.season_id, b.striker
),
bowl AS (
  SELECT m.season_id, b.bowler AS player_id, COUNT(*) AS total_wickets,
         ROW_NUMBER() OVER (PARTITION BY m.season_id ORDER BY COUNT(*) DESC, b.bowler ASC) AS rn
  FROM wicket_taken w
  JOIN ball_by_ball b ON b.match_id = w.match_id AND b.over_id = w.over_id AND b.ball_id = w.ball_id AND b.innings_no = w.innings_no
  JOIN match m ON m.match_id = w.match_id
  WHERE w.kind_out NOT IN ('run out', 'hit wicket', 'retired hurt')
  GROUP BY m.season_id, b.bowler
),
ranks AS (
  SELECT 1 AS rn UNION ALL SELECT 2 UNION ALL SELECT 3
),
seasons AS (
  SELECT DISTINCT season_id FROM match
)
SELECT s.season_id,
       r.rn AS position,
       bat.player_id AS batsman_id,
       pb.player_name AS batsman_name,
       bat.total_runs,
       bowl.player_id AS bowler_id,
       pw.player_name AS bowler_name,
       bowl.total_wickets
FROM seasons s
CROSS JOIN ranks r
LEFT JOIN bat ON bat.season_id = s.season_id AND bat.rn = r.rn
LEFT JOIN bowl ON bowl.season_id = s.season_id AND bowl.rn = r.rn
LEFT JOIN player pb ON pb.player_id = bat.player_id
LEFT JOIN player pw ON pw.player_id = bowl.player_id
ORDER BY s.season_id, r.rn