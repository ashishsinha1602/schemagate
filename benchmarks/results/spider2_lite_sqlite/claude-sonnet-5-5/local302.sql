WITH base AS (
  SELECT 'region' AS attr_type, region AS attr_value, week_date_formatted AS wd, sales FROM cleaned_weekly_sales
  UNION ALL
  SELECT 'platform', platform, week_date_formatted, sales FROM cleaned_weekly_sales
  UNION ALL
  SELECT 'age_band', age_band, week_date_formatted, sales FROM cleaned_weekly_sales
  UNION ALL
  SELECT 'demographic', demographic, week_date_formatted, sales FROM cleaned_weekly_sales
  UNION ALL
  SELECT 'customer_type', customer_type, week_date_formatted, sales FROM cleaned_weekly_sales
),
agg AS (
  SELECT attr_type, attr_value,
    SUM(CASE WHEN wd >= date('2020-06-15','-84 days') AND wd < '2020-06-15' THEN sales END) AS before_sales,
    SUM(CASE WHEN wd >= '2020-06-15' AND wd < date('2020-06-15','+84 days') THEN sales END) AS after_sales
  FROM base
  GROUP BY attr_type, attr_value
),
pct AS (
  SELECT attr_type, attr_value,
    (after_sales - before_sales) * 100.0 / before_sales AS pct_change
  FROM agg
  WHERE before_sales IS NOT NULL AND before_sales <> 0
)
SELECT attr_type, AVG(pct_change) AS avg_pct_change
FROM pct
GROUP BY attr_type
ORDER BY avg_pct_change ASC
LIMIT 1