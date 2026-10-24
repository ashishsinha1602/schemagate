WITH rank_avg AS (
  SELECT FacRank, AVG(FacSalary) AS avg_salary
  FROM university_faculty
  GROUP BY FacRank
),
diffs AS (
  SELECT f.FacRank, f.FacFirstName, f.FacLastName, f.FacSalary,
         ABS(f.FacSalary - r.avg_salary) AS diff,
         RANK() OVER (PARTITION BY f.FacRank ORDER BY ABS(f.FacSalary - r.avg_salary)) AS rnk
  FROM university_faculty f
  JOIN rank_avg r ON f.FacRank = r.FacRank
)
SELECT FacRank, FacFirstName, FacLastName, FacSalary
FROM diffs
WHERE rnk = 1