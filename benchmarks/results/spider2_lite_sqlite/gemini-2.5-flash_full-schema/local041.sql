SELECT
  CAST(SUM(CASE WHEN health = 'Good' THEN 1 ELSE 0 END) AS REAL) * 100 / COUNT(tree_id)
FROM main.trees
WHERE
  boroname = 'Bronx'