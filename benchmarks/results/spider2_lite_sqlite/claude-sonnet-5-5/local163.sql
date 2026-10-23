WITH t AS (
  SELECT FacRank, FacFirstName, FacLastName, FacSalary,
         ABS(FacSalary - AVG(FacSalary) OVER (PARTITION BY FacRank)) AS diff
  FROM university_faculty
),
r AS (
  SELECT *, MIN(diff) OVER (PARTITION BY FacRank) AS mindiff
  FROM t
)
SELECT FacRank, FacFirstName, FacLastName, FacSalary
FROM r
WHERE diff = mindiff