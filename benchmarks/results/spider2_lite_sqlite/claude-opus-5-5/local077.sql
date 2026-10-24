WITH avg_comp AS (
  SELECT
    m._year,
    m._month,
    m.month_year,
    m.interest_id,
    m.composition / m.index_value AS avg_composition
  FROM main.interest_metrics m
  WHERE m.month_year IS NOT NULL
    AND m.index_value IS NOT NULL
    AND m.index_value <> 0
),
ranked AS (
  SELECT
    a.*,
    ROW_NUMBER() OVER (
      PARTITION BY a._year, a._month
      ORDER BY a.avg_composition DESC
    ) AS rn
  FROM avg_comp a
),
monthly_max AS (
  SELECT
    r._year,
    r._month,
    r.month_year,
    im.interest_name,
    r.avg_composition AS max_index_composition
  FROM ranked r
  JOIN main.interest_map im ON im.id = r.interest_id
  WHERE r.rn = 1
),
rolling AS (
  SELECT
    mm.*,
    AVG(mm.max_index_composition) OVER (
      ORDER BY mm._year, mm._month
      ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS rolling_avg,
    LAG(mm.interest_name, 1) OVER (ORDER BY mm._year, mm._month) AS one_month_ago_interest_name,
    LAG(mm.max_index_composition, 1) OVER (ORDER BY mm._year, mm._month) AS one_month_ago_max_index_composition,
    LAG(mm.interest_name, 2) OVER (ORDER BY mm._year, mm._month) AS two_month_ago_interest_name,
    LAG(mm.max_index_composition, 2) OVER (ORDER BY mm._year, mm._month) AS two_month_ago_max_index_composition
  FROM monthly_max mm
)
SELECT
  month_year AS date,
  interest_name,
  ROUND(max_index_composition, 2) AS max_index_composition,
  ROUND(rolling_avg, 2) AS rolling_avg,
  one_month_ago_interest_name,
  ROUND(one_month_ago_max_index_composition, 2) AS one_month_ago_max_index_composition,
  two_month_ago_interest_name,
  ROUND(two_month_ago_max_index_composition, 2) AS two_month_ago_max_index_composition
FROM rolling
WHERE (_year * 100 + _month) BETWEEN 201809 AND 201908
ORDER BY _year, _month