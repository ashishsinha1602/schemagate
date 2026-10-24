WITH valid AS (
  SELECT g.stn, g.wban, COUNT(DISTINCT g.date) AS valid_days
  FROM `bigquery-public-data.noaa_gsod.gsod*` g
  JOIN `bigquery-public-data.noaa_gsod.stations` s
    ON g.stn = s.usaf AND g.wban = s.wban
  WHERE g._TABLE_SUFFIX = '2022'
    AND s.usaf != '999999'
    AND g.temp IS NOT NULL AND g.temp != 9999.9
    AND g.max IS NOT NULL AND g.max != 9999.9
    AND g.min IS NOT NULL AND g.min != 9999.9
  GROUP BY g.stn, g.wban
)
SELECT
  SAFE_DIVIDE(
    100 * (SELECT COUNT(*) FROM valid WHERE valid_days >= 0.9 * 365),
    (SELECT COUNT(*) FROM `bigquery-public-data.noaa_gsod.stations`)
  ) AS percentage_of_stations