WITH bat AS (
  SELECT m.season_id, b.striker AS player_id, SUM(bs.runs_scored) AS total_runs
  FROM batsman_scored bs
  JOIN ball_by_ball b
    ON b.match_id = bs.match_id AND b.over_id = bs.over_id
   AND b.ball_id = bs.ball_id AND b.innings_no = bs.innings_no
  JOIN match m ON m.match_id = bs.match_id
  GROUP BY m.season_id, b.striker
),
bat_rank AS (
  SELECT season_id, player_id, total_runs,
         ROW_NUMBER() OVER (PARTITION BY season_id ORDER BY total_runs DESC, player_id ASC) AS rn
  FROM bat
),
bowl AS (
  SELECT m.season_id, b.bowler AS player_id, COUNT(*) AS total_wickets
  FROM wicket_taken w
  JOIN ball_by_ball b
    ON b.match_id = w.match_id AND b.over_id = w.over_id
   AND b.ball_id = w.ball_id AND b.innings_no = w.innings_no
  JOIN match m ON m.match_id = w.match_id
  WHERE w.kind_out NOT IN ('run out', 'hit wicket', 'retired hurt')
  GROUP BY m.season_id, b.bowler
),
bowl_rank AS (
  SELECT season_id, player_id, total_wickets,
         ROW_NUMBER() OVER (PARTITION BY season_id ORDER BY total_wickets DESC, player_id ASC) AS rn
  FROM bowl
)
SELECT br.season_id,
       br.rn AS position,
       br.player_id AS batsman_id,
       pb.player_name AS batsman_name,
       br.total_runs,
       wr.player_id AS bowler_id,
       pw.player_name AS bowler_name,
       wr.total_wickets
FROM bat_rank br
JOIN bowl_rank wr ON wr.season_id = br.season_id AND wr.rn = br.rn
LEFT JOIN player pb ON pb.player_id = br.player_id
LEFT JOIN player pw ON pw.player_id = wr.player_id
WHERE br.rn <= 3
ORDER BY br.season_id, br.rn