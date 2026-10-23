WITH
  StrikerMatchRuns AS (
    SELECT
      bbb.match_id,
      bbb.striker AS player_id,
      SUM(bs.runs_scored) AS runs_in_match
    FROM main.ball_by_ball AS bbb
    JOIN main.batsman_scored AS bs
      ON bbb.match_id = bs.match_id
      AND bbb.over_id = bs.over_id
      AND bbb.ball_id = bs.ball_id
      AND bbb.innings_no = bs.innings_no
    GROUP BY
      bbb.match_id,
      bbb.striker
  ),
  HighScoringStrikers AS (
    SELECT DISTINCT
      player_id
    FROM StrikerMatchRuns
    WHERE
      runs_in_match > 50
  ),
  TotalRunsForHighScoringStrikers AS (
    SELECT
      smr.player_id,
      SUM(smr.runs_in_match) AS total_career_runs
    FROM StrikerMatchRuns AS smr
    JOIN HighScoringStrikers AS hss
      ON smr.player_id = hss.player_id
    GROUP BY
      smr.player_id
  )
SELECT
  AVG(total_career_runs)
FROM TotalRunsForHighScoringStrikers