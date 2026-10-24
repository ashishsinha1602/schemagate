WITH irish AS (
  SELECT id
  FROM `bigquery-public-data.ncaa_basketball.mbb_teams`
  WHERE name = 'Fighting Irish'
),
plays AS (
  SELECT
    p.game_id,
    p.period,
    p.game_clock,
    p.team_name,
    p.event_description,
    p.event_id,
    p.points_scored,
    p.team_id,
    p.home_id,
    p.away_id,
    COALESCE(SAFE_CAST(SPLIT(p.game_clock, ':')[SAFE_OFFSET(0)] AS INT64), 0) * 60
      + COALESCE(SAFE_CAST(SPLIT(p.game_clock, ':')[SAFE_OFFSET(1)] AS INT64), 0) AS clock_sec
  FROM `bigquery-public-data.ncaa_basketball.mbb_pbp_sr` AS p
  WHERE p.season = 2014
    AND p.home_name = 'Wildcats'
    AND p.away_id IN (SELECT id FROM irish)
    AND p.points_scored > 0
)
SELECT
  game_clock,
  SUM(IF(team_id = home_id, points_scored, 0)) OVER (PARTITION BY game_id ORDER BY period ASC, clock_sec DESC, event_id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS wildcats_score,
  SUM(IF(team_id = away_id, points_scored, 0)) OVER (PARTITION BY game_id ORDER BY period ASC, clock_sec DESC, event_id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS fighting_irish_score,
  team_name,
  event_description
FROM plays
ORDER BY game_id, period ASC, clock_sec DESC, event_id