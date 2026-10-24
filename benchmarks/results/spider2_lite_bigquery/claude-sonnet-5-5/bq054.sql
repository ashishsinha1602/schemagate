WITH t AS (
  SELECT
    UPPER(TRIM(spc_latin)) AS latin_name,
    spc_common,
    _TABLE_SUFFIX AS yr,
    status
  FROM `bigquery-public-data.new_york.tree_census_*`
  WHERE _TABLE_SUFFIX IN ('1995', '2005', '2015')
    AND spc_latin IS NOT NULL
    AND TRIM(spc_latin) != ''
)
SELECT
  latin_name,
  MAX(spc_common) AS common_name,
  COUNT(*) AS total_trees,
  COUNTIF(yr = '1995') AS total_1995,
  COUNTIF(yr = '2005') AS total_2005,
  COUNTIF(yr = '2015') AS total_2015,
  COUNTIF(yr = '1995' AND status = 'Alive') AS alive_1995,
  COUNTIF(yr = '1995' AND status = 'Dead') AS dead_1995,
  COUNTIF(yr = '2005' AND status = 'Alive') AS alive_2005,
  COUNTIF(yr = '2005' AND status = 'Dead') AS dead_2005,
  COUNTIF(yr = '2015' AND status = 'Alive') AS alive_2015,
  COUNTIF(yr = '2015' AND status = 'Dead') AS dead_2015,
  COUNTIF(yr = '2015' AND status = 'Alive') - COUNTIF(yr = '1995' AND status = 'Alive') AS alive_growth_1995_2015,
  COUNTIF(yr = '2015' AND status = 'Dead') - COUNTIF(yr = '1995' AND status = 'Dead') AS dead_growth_1995_2015,
  COUNTIF(yr = '2015') - COUNTIF(yr = '1995') AS total_growth_1995_2015
FROM t
GROUP BY latin_name
ORDER BY total_growth_1995_2015 DESC
LIMIT 10