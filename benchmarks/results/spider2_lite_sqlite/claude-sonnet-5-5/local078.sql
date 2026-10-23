WITH best AS (
  SELECT interest_id, month_year, composition,
         ROW_NUMBER() OVER (PARTITION BY interest_id ORDER BY composition DESC) AS rn
  FROM interest_metrics
  WHERE interest_id IS NOT NULL AND composition IS NOT NULL
),
ranked AS (
  SELECT b.month_year, m.interest_name, b.composition,
         ROW_NUMBER() OVER (ORDER BY b.composition DESC, m.interest_name) AS rd,
         ROW_NUMBER() OVER (ORDER BY b.composition ASC, m.interest_name) AS ra
  FROM best b
  JOIN interest_map m ON m.id = b.interest_id
  WHERE b.rn = 1
)
SELECT month_year AS "time(MM-YYYY)", interest_name, composition
FROM ranked
WHERE rd <= 10 OR ra <= 10
ORDER BY composition DESC, interest_name