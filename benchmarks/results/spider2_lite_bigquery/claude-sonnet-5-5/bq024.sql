WITH j AS (
  SELECT
    p.evaluation_group,
    p.evaluation_type,
    c.condition_status_code,
    p.evaluation_description,
    p.state_code,
    c.macroplot_proportion_unadjusted * p.adjustment_factor_for_the_macroplot AS macroplot_acres,
    c.subplot_proportion_unadjusted * p.adjustment_factor_for_the_subplot AS subplot_acres
  FROM `bigquery-public-data.usfs_fia.condition` c
  JOIN `bigquery-public-data.usfs_fia.population` p
    ON c.state_code = p.state_code
   AND c.survey_unit_code = p.survey_unit_code
   AND c.county_code = p.county_code
   AND c.inventory_year = p.inventory_year
  WHERE p.inventory_year = 2012
),
ranked AS (
  SELECT j.*,
    ROW_NUMBER() OVER (PARTITION BY evaluation_group ORDER BY subplot_acres DESC) AS rn
  FROM j
)
SELECT
  evaluation_group,
  evaluation_type,
  condition_status_code,
  evaluation_description,
  state_code,
  macroplot_acres,
  subplot_acres
FROM ranked
WHERE rn = 1
ORDER BY subplot_acres DESC
LIMIT 10