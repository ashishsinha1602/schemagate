WITH yearly AS (
  SELECT strftime('%Y', collision_date) AS yr,
         pcf_violation_category AS cat,
         COUNT(*) AS n
  FROM collisions
  WHERE strftime('%Y', collision_date) IN ('2011', '2021')
  GROUP BY yr, cat
),
totals AS (
  SELECT yr, SUM(n) AS tot
  FROM yearly
  GROUP BY yr
),
top_cat AS (
  SELECT cat
  FROM yearly
  WHERE yr = '2021' AND cat IS NOT NULL
  ORDER BY n DESC
  LIMIT 1
),
shares AS (
  SELECT y.yr, 100.0 * y.n / t.tot AS share
  FROM yearly y
  JOIN totals t ON t.yr = y.yr
  WHERE y.cat = (SELECT cat FROM top_cat)
)
SELECT (SELECT cat FROM top_cat) AS pcf_violation_category,
       (SELECT share FROM shares WHERE yr = '2011') AS share_2011_pct,
       (SELECT share FROM shares WHERE yr = '2021') AS share_2021_pct,
       (SELECT share FROM shares WHERE yr = '2011') - (SELECT share FROM shares WHERE yr = '2021') AS percentage_point_decrease