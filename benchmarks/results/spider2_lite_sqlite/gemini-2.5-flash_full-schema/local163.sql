WITH RankAvgSalary AS (
  SELECT
    FacRank,
    AVG(FacSalary) AS AvgSalary
  FROM main.university_faculty
  GROUP BY
    FacRank
)
SELECT
  T1.FacRank,
  T1.FacFirstName,
  T1.FacLastName,
  T1.FacSalary
FROM main.university_faculty AS T1
INNER JOIN RankAvgSalary AS T2
  ON T1.FacRank = T2.FacRank
ORDER BY
  ABS(T1.FacSalary - T2.AvgSalary)
LIMIT 100