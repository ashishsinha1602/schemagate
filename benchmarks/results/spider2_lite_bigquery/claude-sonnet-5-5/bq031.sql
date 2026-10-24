WITH base AS (
  SELECT
    date,
    IF(temp = 9999.9, NULL, (temp - 32) * 5 / 9) AS temp_c,
    IF(prcp = 99.99, NULL, prcp * 2.54) AS prcp_cm,
    IF(SAFE_CAST(wdsp AS FLOAT64) = 999.9, NULL, SAFE_CAST(wdsp AS FLOAT64) * 0.514444) AS wind_ms
  FROM `bigquery-public-data.noaa_gsod.gsod*`
  WHERE _TABLE_SUFFIX = '2019'
    AND stn = '726440'
    AND wban = '14925'
    AND date BETWEEN '2019-01-01' AND '2019-03-31'
),
ma AS (
  SELECT
    date, temp_c, prcp_cm, wind_ms,
    AVG(temp_c) OVER (ORDER BY date ROWS BETWEEN 7 PRECEDING AND CURRENT ROW) AS ma_temp,
    AVG(prcp_cm) OVER (ORDER BY date ROWS BETWEEN 7 PRECEDING AND CURRENT ROW) AS ma_prcp,
    AVG(wind_ms) OVER (ORDER BY date ROWS BETWEEN 7 PRECEDING AND CURRENT ROW) AS ma_wind
  FROM base
),
lags AS (
  SELECT
    date, temp_c, prcp_cm, wind_ms, ma_temp, ma_prcp, ma_wind,
    ma_temp - LAG(ma_temp, 1) OVER w AS temp_diff_lag1,
    ma_temp - LAG(ma_temp, 2) OVER w AS temp_diff_lag2,
    ma_temp - LAG(ma_temp, 3) OVER w AS temp_diff_lag3,
    ma_temp - LAG(ma_temp, 4) OVER w AS temp_diff_lag4,
    ma_temp - LAG(ma_temp, 5) OVER w AS temp_diff_lag5,
    ma_temp - LAG(ma_temp, 6) OVER w AS temp_diff_lag6,
    ma_temp - LAG(ma_temp, 7) OVER w AS temp_diff_lag7,
    ma_temp - LAG(ma_temp, 8) OVER w AS temp_diff_lag8,
    ma_prcp - LAG(ma_prcp, 1) OVER w AS prcp_diff_lag1,
    ma_prcp - LAG(ma_prcp, 2) OVER w AS prcp_diff_lag2,
    ma_prcp - LAG(ma_prcp, 3) OVER w AS prcp_diff_lag3,
    ma_prcp - LAG(ma_prcp, 4) OVER w AS prcp_diff_lag4,
    ma_prcp - LAG(ma_prcp, 5) OVER w AS prcp_diff_lag5,
    ma_prcp - LAG(ma_prcp, 6) OVER w AS prcp_diff_lag6,
    ma_prcp - LAG(ma_prcp, 7) OVER w AS prcp_diff_lag7,
    ma_prcp - LAG(ma_prcp, 8) OVER w AS prcp_diff_lag8,
    ma_wind - LAG(ma_wind, 1) OVER w AS wind_diff_lag1,
    ma_wind - LAG(ma_wind, 2) OVER w AS wind_diff_lag2,
    ma_wind - LAG(ma_wind, 3) OVER w AS wind_diff_lag3,
    ma_wind - LAG(ma_wind, 4) OVER w AS wind_diff_lag4,
    ma_wind - LAG(ma_wind, 5) OVER w AS wind_diff_lag5,
    ma_wind - LAG(ma_wind, 6) OVER w AS wind_diff_lag6,
    ma_wind - LAG(ma_wind, 7) OVER w AS wind_diff_lag7,
    ma_wind - LAG(ma_wind, 8) OVER w AS wind_diff_lag8
  FROM ma
  WINDOW w AS (ORDER BY date)
)
SELECT
  date,
  ROUND(temp_c, 1) AS temp_c,
  ROUND(prcp_cm, 1) AS prcp_cm,
  ROUND(wind_ms, 1) AS wind_ms,
  ROUND(ma_temp, 1) AS ma_temp,
  ROUND(ma_prcp, 1) AS ma_prcp,
  ROUND(ma_wind, 1) AS ma_wind,
  ROUND(temp_diff_lag1, 1) AS temp_diff_lag1,
  ROUND(temp_diff_lag2, 1) AS temp_diff_lag2,
  ROUND(temp_diff_lag3, 1) AS temp_diff_lag3,
  ROUND(temp_diff_lag4, 1) AS temp_diff_lag4,
  ROUND(temp_diff_lag5, 1) AS temp_diff_lag5,
  ROUND(temp_diff_lag6, 1) AS temp_diff_lag6,
  ROUND(temp_diff_lag7, 1) AS temp_diff_lag7,
  ROUND(temp_diff_lag8, 1) AS temp_diff_lag8,
  ROUND(prcp_diff_lag1, 1) AS prcp_diff_lag1,
  ROUND(prcp_diff_lag2, 1) AS prcp_diff_lag2,
  ROUND(prcp_diff_lag3, 1) AS prcp_diff_lag3,
  ROUND(prcp_diff_lag4, 1) AS prcp_diff_lag4,
  ROUND(prcp_diff_lag5, 1) AS prcp_diff_lag5,
  ROUND(prcp_diff_lag6, 1) AS prcp_diff_lag6,
  ROUND(prcp_diff_lag7, 1) AS prcp_diff_lag7,
  ROUND(prcp_diff_lag8, 1) AS prcp_diff_lag8,
  ROUND(wind_diff_lag1, 1) AS wind_diff_lag1,
  ROUND(wind_diff_lag2, 1) AS wind_diff_lag2,
  ROUND(wind_diff_lag3, 1) AS wind_diff_lag3,
  ROUND(wind_diff_lag4, 1) AS wind_diff_lag4,
  ROUND(wind_diff_lag5, 1) AS wind_diff_lag5,
  ROUND(wind_diff_lag6, 1) AS wind_diff_lag6,
  ROUND(wind_diff_lag7, 1) AS wind_diff_lag7,
  ROUND(wind_diff_lag8, 1) AS wind_diff_lag8
FROM lags
WHERE date >= '2019-01-09'
ORDER BY date