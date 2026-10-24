WITH w AS (
  SELECT
    EXTRACT(YEAR FROM SAFE_CAST(date AS DATE)) AS yr,
    SAFE_CAST(symptom_anosmia AS FLOAT64) AS anosmia
  FROM `bigquery-public-data.covid19_symptom_search.symptom_search_sub_region_2_weekly`
  WHERE sub_region_2 IN ('Bronx County', 'Queens County', 'Kings County', 'New York County', 'Richmond County')
    AND SAFE_CAST(date AS DATE) BETWEEN DATE '2019-01-01' AND DATE '2020-12-31'
),
a AS (
  SELECT
    AVG(IF(yr = 2019, anosmia, NULL)) AS avg_2019,
    AVG(IF(yr = 2020, anosmia, NULL)) AS avg_2020
  FROM w
)
SELECT
  SAFE_DIVIDE(avg_2020 - avg_2019, avg_2019) * 100 AS percent_change
FROM a