WITH monthly AS (
  SELECT _year, _month, month_year, interest_id,
         AVG(composition / index_value) AS avg_comp
  FROM interest_metrics
  WHERE index_value IS NOT NULL AND index_value <> 0
    AND ((_year = 2018 AND _month >= 9) OR (_year = 2019 AND _month <= 8))
  GROUP BY _year, _month, month_year, interest_id
),
ranked AS (
  SELECT m.*, ROW_NUMBER() OVER (PARTITION BY _year, _month ORDER BY avg_comp DESC, interest_id) AS rn
  FROM monthly m
),
top AS (
  SELECT r._year, r._month, r.month_year, im.interest_name, r.avg_comp AS max_index_composition
  FROM ranked r
  LEFT JOIN interest_map im ON im.id = r.interest_id
  WHERE r.rn = 1
)
SELECT month_year AS date,
       interest_name,
       max_index_composition,
       AVG(max_index_composition) OVER (ORDER BY _year, _month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS three_month_rolling_avg,
       LAG(interest_name, 1) OVER (ORDER BY _year, _month) AS one_month_ago_interest_name,
       LAG(max_index_composition, 1) OVER (ORDER BY _year, _month) AS one_month_ago_max_index_composition,
       LAG(interest_name, 2) OVER (ORDER BY _year, _month) AS two_months_ago_interest_name,
       LAG(max_index_composition, 2) OVER (ORDER BY _year, _month) AS two_months_ago_max_index_composition
FROM top
ORDER BY _year, _month