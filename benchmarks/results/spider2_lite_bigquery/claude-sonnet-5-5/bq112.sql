WITH w AS (
  SELECT 1998 AS yr, avg_wkly_wage_10_total_all_industries AS wk FROM `bigquery-public-data.bls_qcew.1998_q1` WHERE area_fips = '42003'
  UNION ALL SELECT 1998, avg_wkly_wage_10_total_all_industries FROM `bigquery-public-data.bls_qcew.1998_q2` WHERE area_fips = '42003'
  UNION ALL SELECT 1998, avg_wkly_wage_10_total_all_industries FROM `bigquery-public-data.bls_qcew.1998_q3` WHERE area_fips = '42003'
  UNION ALL SELECT 1998, avg_wkly_wage_10_total_all_industries FROM `bigquery-public-data.bls_qcew.1998_q4` WHERE area_fips = '42003'
  UNION ALL SELECT 2017, avg_wkly_wage_10_total_all_industries FROM `bigquery-public-data.bls_qcew.2017_q1` WHERE area_fips = '42003'
  UNION ALL SELECT 2017, avg_wkly_wage_10_total_all_industries FROM `bigquery-public-data.bls_qcew.2017_q2` WHERE area_fips = '42003'
  UNION ALL SELECT 2017, avg_wkly_wage_10_total_all_industries FROM `bigquery-public-data.bls_qcew.2017_q3` WHERE area_fips = '42003'
  UNION ALL SELECT 2017, avg_wkly_wage_10_total_all_industries FROM `bigquery-public-data.bls_qcew.2017_q4` WHERE area_fips = '42003'
),
wy AS (
  SELECT yr, AVG(wk) * 52 AS annual_wage
  FROM w
  GROUP BY yr
),
c AS (
  SELECT year AS yr, AVG(value) AS cpi
  FROM `bigquery-public-data.bls.cpi_u`
  WHERE item_name = 'All items'
    AND area_name = 'U.S. city average'
    AND seasonal_code = 'U'
    AND period != 'M13'
    AND year IN (1998, 2017)
  GROUP BY year
)
SELECT
  ROUND(100 * SAFE_DIVIDE(MAX(IF(wy.yr = 2017, wy.annual_wage, NULL)) - MAX(IF(wy.yr = 1998, wy.annual_wage, NULL)), MAX(IF(wy.yr = 1998, wy.annual_wage, NULL))), 2) AS wage_growth_pct,
  ROUND(100 * SAFE_DIVIDE(MAX(IF(c.yr = 2017, c.cpi, NULL)) - MAX(IF(c.yr = 1998, c.cpi, NULL)), MAX(IF(c.yr = 1998, c.cpi, NULL))), 2) AS cpi_growth_pct,
  ROUND(100 * SAFE_DIVIDE(MAX(IF(wy.yr = 2017, wy.annual_wage, NULL)) - MAX(IF(wy.yr = 1998, wy.annual_wage, NULL)), MAX(IF(wy.yr = 1998, wy.annual_wage, NULL))), 2)
    >= ROUND(100 * SAFE_DIVIDE(MAX(IF(c.yr = 2017, c.cpi, NULL)) - MAX(IF(c.yr = 1998, c.cpi, NULL)), MAX(IF(c.yr = 1998, c.cpi, NULL))), 2) AS wages_kept_pace
FROM wy
JOIN c ON wy.yr = c.yr