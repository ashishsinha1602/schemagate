WITH base AS (
  SELECT
    state_name,
    commodity_desc,
    unit_desc,
    value
  FROM `bigquery-public-data.usda_nass_agriculture.crops`
  WHERE year = 2022
    AND statisticcat_desc = 'PRODUCTION'
    AND agg_level_desc = 'STATE'
    AND value IS NOT NULL
    AND (
      (commodity_desc = 'CORN' AND group_desc = 'FIELD CROPS' AND unit_desc = 'BU')
      OR (commodity_desc = 'MUSHROOMS' AND group_desc = 'HORTICULTURE')
    )
)
SELECT
  state_name,
  SUM(IF(commodity_desc = 'CORN', value, NULL)) AS corn_production_2022,
  SUM(IF(commodity_desc = 'MUSHROOMS', value, NULL)) AS mushroom_production_2022
FROM base
GROUP BY state_name
ORDER BY state_name