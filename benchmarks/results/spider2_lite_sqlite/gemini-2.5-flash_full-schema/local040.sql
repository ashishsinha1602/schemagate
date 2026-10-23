WITH ValidTrees AS (
  SELECT
    t.boroname,
    t.tree_id,
    i.Estimate_Median_income,
    i.Estimate_Mean_income
  FROM main.trees AS t
  JOIN main.income_trees AS i
    ON t.zipcode = i.zipcode
  WHERE
    i.Estimate_Median_income > 0 AND i.Estimate_Mean_income > 0 AND t.boroname IS NOT NULL AND t.boroname != ''
)
SELECT
  boroname,
  COUNT(tree_id) AS number_of_trees,
  AVG(Estimate_Mean_income) AS average_mean_income
FROM ValidTrees
GROUP BY
  boroname
ORDER BY
  number_of_trees DESC
LIMIT 3