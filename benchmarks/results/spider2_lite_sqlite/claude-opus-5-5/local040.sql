SELECT t.boroname,
       COUNT(t.tree_id) AS tree_count,
       AVG(i.Estimate_Mean_income) AS avg_mean_income
FROM trees t
JOIN income_trees i
  ON i.zipcode = t.zipcode
WHERE i.Estimate_Median_income > 0
  AND i.Estimate_Mean_income > 0
  AND t.boroname IS NOT NULL
  AND TRIM(t.boroname) <> ''
GROUP BY t.boroname
ORDER BY tree_count DESC
LIMIT 3