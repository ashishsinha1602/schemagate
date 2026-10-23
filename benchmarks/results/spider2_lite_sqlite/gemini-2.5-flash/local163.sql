WITH RankAvgSalary AS (
  SELECT
    FacRank,
    AVG(FacSalary) AS AvgRankSalary
  FROM main.university_faculty
  GROUP BY
    FacRank
), FacultySalaryDiff AS (
  SELECT
    f.FacRank,
    f.FacFirstName,
    f.FacLastName,
    f.FacSalary,
    ABS(f.FacSalary - ras.AvgRankSalary) AS SalaryDifference
  FROM main.university_faculty AS f
  JOIN RankAvgSalary AS ras
    ON f.FacRank = ras.FacRank
), MinDiffPerRank AS (
  SELECT
    FacRank,
    MIN(SalaryDifference) AS MinSalaryDifference
  FROM FacultySalaryDiff
  GROUP BY
    FacRank
)
SELECT
  fsd.FacRank,
  fsd.FacFirstName,
  fsd.FacLastName,
  fsd.FacSalary
FROM FacultySalaryDiff AS fsd
JOIN MinDiffPerRank AS mdr
  ON fsd.FacRank = mdr.FacRank
  AND fsd.SalaryDifference = mdr.MinSalaryDifference