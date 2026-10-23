WITH j AS (
  SELECT t.boroname, i.Estimate_Mean_income
  FROM trees t
  JOIN income_trees i ON i.zipcode = t.zipcode
  WHERE i.Estimate_Median_income > 0
    AND i.Estimate_Mean_income > 0
    AND t.boroname IS NOT NULL
    AND TRIM(t.boroname) <> ''
)
SELECT boroname, COUNT(*) AS tree_count, AVG(Estimate_Mean_income) AS avg_mean_income
FROM j
GROUP BY boroname
ORDER BY tree_count DESC
LIMIT 3