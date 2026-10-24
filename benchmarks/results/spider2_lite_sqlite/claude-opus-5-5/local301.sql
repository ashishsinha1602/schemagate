WITH params AS (
  SELECT 2018 AS yr, '2018-06-15' AS ref_date
  UNION ALL SELECT 2019, '2019-06-15'
  UNION ALL SELECT 2020, '2020-06-15'
),
agg AS (
  SELECT p.yr,
         SUM(CASE WHEN date(c.week_date_formatted) >= date(p.ref_date, '-28 days')
                   AND date(c.week_date_formatted) < date(p.ref_date)
                  THEN c.sales ELSE 0 END) AS before_sales,
         SUM(CASE WHEN date(c.week_date_formatted) >= date(p.ref_date)
                   AND date(c.week_date_formatted) < date(p.ref_date, '+28 days')
                  THEN c.sales ELSE 0 END) AS after_sales
  FROM params p
  JOIN cleaned_weekly_sales c
    ON date(c.week_date_formatted) >= date(p.ref_date, '-28 days')
   AND date(c.week_date_formatted) < date(p.ref_date, '+28 days')
  GROUP BY p.yr
)
SELECT yr AS calendar_year,
       before_sales,
       after_sales,
       ROUND(100.0 * (after_sales - before_sales) / before_sales, 2) AS pct_change
FROM agg
ORDER BY yr