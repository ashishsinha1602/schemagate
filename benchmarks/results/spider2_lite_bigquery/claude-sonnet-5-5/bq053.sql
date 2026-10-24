WITH s AS (
  SELECT UPPER(species_scientific_name) AS sp, ANY_VALUE(fall_color) AS fall_color
  FROM `bigquery-public-data.new_york.tree_species`
  GROUP BY sp
),
t95 AS (
  SELECT UPPER(spc_latin) AS sp, COUNT(*) AS n
  FROM `bigquery-public-data.new_york.tree_census_*`
  WHERE _TABLE_SUFFIX = '1995' AND status != 'Dead'
  GROUP BY sp
),
t15 AS (
  SELECT UPPER(spc_latin) AS sp, COUNT(*) AS n
  FROM `bigquery-public-data.new_york.tree_census_*`
  WHERE _TABLE_SUFFIX = '2015' AND status = 'Alive'
  GROUP BY sp
)
SELECT s.fall_color,
       SUM(COALESCE(t95.n, 0) - COALESCE(t15.n, 0)) AS total_change
FROM s
LEFT JOIN t95 ON t95.sp = s.sp
LEFT JOIN t15 ON t15.sp = s.sp
GROUP BY s.fall_color