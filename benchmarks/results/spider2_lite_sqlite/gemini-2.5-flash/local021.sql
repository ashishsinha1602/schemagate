WITH StrikerMatchRuns AS (
  SELECT
    bbb.match_id,
    bbb.striker AS player_id,
    SUM(bs.runs_scored) AS total_runs_in_match
  FROM main.ball_by_ball AS bbb
  JOIN main.batsman_scored AS bs
    ON bbb.match_id = bs.match_id
    AND bbb.over_id = bs.over_id
    AND bbb.ball_id = bs.ball_id
    AND bbb.innings_no = bs.innings_no
  GROUP BY
    bbb.match_id,
    bbb.striker
), HighScoringStrikers AS (
  SELECT DISTINCT
    player_id
  FROM StrikerMatchRuns
  WHERE
    total_runs_in_match > 50
), AllRunsForHighScoringStrikers AS (
  SELECT
    bbb.striker AS player_id,
    SUM(bs.runs_scored) AS total_career_runs
  FROM main.ball_by_ball AS bbb
  JOIN main.batsman_scored AS bs
    ON bbb.match_id = bs.match_id
    AND bbb.over_id = bs.over_id
    AND bbb.ball_id = bs.ball_id
    AND bbb.innings_no = bs.innings_no
  WHERE
    bbb.striker IN (
      SELECT
        player_id
      FROM HighScoringStrikers
    )
  GROUP BY
    bbb.striker
)
SELECT
  AVG(total_career_runs)
FROM AllRunsForHighScoringStrikers