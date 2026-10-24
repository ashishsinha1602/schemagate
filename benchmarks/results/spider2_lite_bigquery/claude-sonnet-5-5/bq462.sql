WITH venues AS (
  SELECT 1 AS cat_order, 'Top Venues' AS Category, 'N/A' AS Date, venue_name AS Matchup_or_Venue, MAX(venue_capacity) AS Key_Metric
  FROM `bigquery-public-data.ncaa_basketball.mbb_teams`
  WHERE venue_name IS NOT NULL AND venue_capacity IS NOT NULL
  GROUP BY venue_name
  ORDER BY Key_Metric DESC
  LIMIT 5
),
margins AS (
  SELECT 2 AS cat_order, 'Biggest Championship Margins' AS Category, CAST(game_date AS STRING) AS Date,
         CONCAT(win_market, ' vs ', lose_market) AS Matchup_or_Venue, win_pts - lose_pts AS Key_Metric
  FROM `bigquery-public-data.ncaa_basketball.mbb_historical_tournament_games`
  WHERE round = 2 AND season > 2015
  ORDER BY Key_Metric DESC
  LIMIT 5
),
scoring AS (
  SELECT 3 AS cat_order, 'Highest Scoring Games' AS Category, scheduled_date AS Date,
         CONCAT(market, ' vs ', opp_market) AS Matchup_or_Venue, points_game + opp_points_game AS Key_Metric
  FROM `bigquery-public-data.ncaa_basketball.mbb_historical_teams_games`
  WHERE season > 2010 AND team_id < opp_id AND points_game IS NOT NULL AND opp_points_game IS NOT NULL
  ORDER BY Key_Metric DESC
  LIMIT 5
),
threes AS (
  SELECT 4 AS cat_order, 'Total Threes' AS Category, CAST(DATE(MAX(scheduled_date)) AS STRING) AS Date,
         STRING_AGG(DISTINCT team_market, ' vs ') AS Matchup_or_Venue,
         COUNTIF(shot_made AND three_point_shot) AS Key_Metric
  FROM `bigquery-public-data.ncaa_basketball.mbb_pbp_sr`
  WHERE season > 2010
  GROUP BY game_id
  ORDER BY Key_Metric DESC
  LIMIT 5
)
SELECT Category, Date, Matchup_or_Venue AS `Matchup or Venue`, Key_Metric AS `Key Metric`
FROM (
  SELECT * FROM venues
  UNION ALL SELECT * FROM margins
  UNION ALL SELECT * FROM scoring
  UNION ALL SELECT * FROM threes
)
ORDER BY cat_order, Key_Metric DESC