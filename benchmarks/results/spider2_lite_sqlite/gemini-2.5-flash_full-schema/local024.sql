WITH player_match_runs AS (
  SELECT
    bb.striker AS player_id,
    bb.match_id,
    SUM(bs.runs_scored) AS total_runs_in_match
  FROM main.ball_by_ball AS bb
  JOIN main.batsman_scored AS bs
    ON bb.match_id = bs.match_id
    AND bb.over_id = bs.over_id
    AND bb.ball_id = bs.ball_id
    AND bb.innings_no = bs.innings_no
  GROUP BY
    bb.striker,
    bb.match_id
), player_averages AS (
  SELECT
    pmr.player_id,
    AVG(pmr.total_runs_in_match) AS player_avg_runs_per_match
  FROM player_match_runs AS pmr
  GROUP BY
    pmr.player_id
)
SELECT
  p.country_name,
  AVG(pa.player_avg_runs_per_match) AS country_batting_average
FROM player_averages AS pa
JOIN main.player AS p
  ON pa.player_id = p.player_id
GROUP BY
  p.country_name
ORDER BY
  country_batting_average DESC
LIMIT 5