WITH shots AS (
  SELECT
    shot_type,
    CASE WHEN event_coord_x < 564 THEN event_coord_x ELSE 1128 - event_coord_x END AS x,
    CASE WHEN event_coord_x < 564 THEN 600 - event_coord_y ELSE event_coord_y END AS y,
    shot_made
  FROM `bigquery-public-data.ncaa_basketball.mbb_pbp_sr`
  WHERE shot_type IS NOT NULL
    AND event_coord_x IS NOT NULL
    AND event_coord_y IS NOT NULL
    AND scheduled_date < TIMESTAMP('2018-03-15')
    AND ((team_basket = 'left' AND event_coord_x < 564)
      OR (team_basket = 'right' AND event_coord_x >= 564))
),
grouped AS (
  SELECT
    shot_type,
    x,
    y,
    COUNT(*) AS shot_attempts,
    SUM(CAST(shot_made AS INT64)) AS shots_made
  FROM shots
  GROUP BY shot_type, x, y
)
SELECT
  shot_type,
  AVG(x) AS avg_x,
  AVG(y) AS avg_y,
  AVG(shot_attempts) AS avg_shot_attempts,
  AVG(shots_made) AS avg_shots_made
FROM grouped
GROUP BY shot_type