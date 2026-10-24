WITH latest AS (
  SELECT state_code, MAX(evaluation_group) AS evaluation_group
  FROM `bigquery-public-data.usfs_fia.population`
  WHERE evaluation_type = 'EXPCURR'
  GROUP BY state_code
),
pop_agg AS (
  SELECT
    p.state_code,
    p.evaluation_group,
    SUM(IF(p.adjustment_factor_for_the_macroplot > 0, p.expansion_factor * p.adjustment_factor_for_the_macroplot, 0)) AS macr_factor,
    SUM(IF(p.adjustment_factor_for_the_subplot > 0, p.expansion_factor * p.adjustment_factor_for_the_subplot, 0)) AS subp_factor
  FROM `bigquery-public-data.usfs_fia.population` p
  JOIN latest l
    ON p.state_code = l.state_code AND p.evaluation_group = l.evaluation_group
  WHERE p.evaluation_type = 'EXPCURR'
  GROUP BY p.state_code, p.evaluation_group
),
state_names AS (
  SELECT plot_state_code AS state_code, ANY_VALUE(plot_state_code_name) AS state_name
  FROM `bigquery-public-data.usfs_fia.plot`
  GROUP BY plot_state_code
),
acres AS (
  SELECT
    pa.state_code,
    pa.evaluation_group,
    SUM(
      IF(c.condition_status_code = 1 AND c.reserved_status_code = 0 AND c.site_productivity_class_code BETWEEN 1 AND 6,
        CASE c.proportion_basis
          WHEN 'MACR' THEN c.condition_proportion_unadjusted * pa.macr_factor
          WHEN 'SUBP' THEN c.condition_proportion_unadjusted * pa.subp_factor
          ELSE 0
        END, 0)
    ) AS timberland_acres,
    SUM(
      IF(c.condition_status_code = 1,
        CASE c.proportion_basis
          WHEN 'MACR' THEN c.condition_proportion_unadjusted * pa.macr_factor
          WHEN 'SUBP' THEN c.condition_proportion_unadjusted * pa.subp_factor
          ELSE 0
        END, 0)
    ) AS forestland_acres
  FROM `bigquery-public-data.usfs_fia.condition` c
  JOIN pop_agg pa
    ON c.state_code = pa.state_code
  GROUP BY pa.state_code, pa.evaluation_group
),
timber AS (
  SELECT 'timberland' AS category, a.state_code, a.evaluation_group, n.state_name, a.timberland_acres AS total_acres
  FROM acres a
  LEFT JOIN state_names n ON a.state_code = n.state_code
  ORDER BY a.timberland_acres DESC
  LIMIT 1
),
forest AS (
  SELECT 'forestland' AS category, a.state_code, a.evaluation_group, n.state_name, a.forestland_acres AS total_acres
  FROM acres a
  LEFT JOIN state_names n ON a.state_code = n.state_code
  ORDER BY a.forestland_acres DESC
  LIMIT 1
)
SELECT * FROM timber
UNION ALL
SELECT * FROM forest