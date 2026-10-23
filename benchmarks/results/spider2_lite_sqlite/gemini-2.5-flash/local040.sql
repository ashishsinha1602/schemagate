SELECT
  T.boroname,
  COUNT(T.tree_id) AS number_of_trees,
  AVG(IT.Estimate_Mean_income) AS average_mean_income
FROM main.trees AS T
JOIN main.income_trees AS IT
  ON T.zipcode = IT.zipcode
WHERE
  IT.Estimate_Median_income > 0 AND IT.Estimate_Mean_income > 0 AND T.boroname IS NOT NULL
GROUP BY
  T.boroname
ORDER BY
  number_of_trees DESC
LIMIT 3