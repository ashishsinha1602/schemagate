SELECT
  s.stprba AS state,
  SUM(n.value) / 1e9 AS total_revenue_billions
FROM `bigquery-public-data.sec_quarterly_financials.numbers` n
JOIN `bigquery-public-data.sec_quarterly_financials.submission` s
  ON n.submission_number = s.submission_number
WHERE n._PARTITIONTIME BETWEEN TIMESTAMP('2016-01-01') AND TIMESTAMP('2017-12-31')
  AND s._PARTITIONTIME BETWEEN TIMESTAMP('2016-01-01') AND TIMESTAMP('2017-12-31')
  AND s.fiscal_year = 2016
  AND n.number_of_quarters = 4
  AND n.measure_tag IN ('Revenues', 'SalesRevenueNet', 'SalesRevenueGoodsNet')
  AND s.stprba IS NOT NULL
  AND TRIM(s.stprba) != ''
GROUP BY s.stprba
ORDER BY total_revenue_billions DESC
LIMIT 1