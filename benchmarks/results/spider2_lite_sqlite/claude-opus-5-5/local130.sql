WITH eng AS (
  SELECT s.StudLastName, ss.Grade
  FROM Student_Schedules ss
  JOIN Students s ON s.StudentID = ss.StudentID
  JOIN Classes c ON c.ClassID = ss.ClassID
  JOIN Subjects sub ON sub.SubjectID = c.SubjectID
  WHERE ss.ClassStatus = 2
    AND sub.CategoryID = 'ENG'
),
ranked AS (
  SELECT e.StudLastName, e.Grade,
    (SELECT COUNT(*) FROM eng e2 WHERE e2.Grade >= e.Grade) AS rnk,
    (SELECT COUNT(*) FROM eng) AS total
  FROM eng e
)
SELECT StudLastName,
  CASE
    WHEN CAST(rnk AS REAL) / total <= 0.2 THEN 'First'
    WHEN CAST(rnk AS REAL) / total <= 0.4 THEN 'Second'
    WHEN CAST(rnk AS REAL) / total <= 0.6 THEN 'Third'
    WHEN CAST(rnk AS REAL) / total <= 0.8 THEN 'Fourth'
    ELSE 'Fifth'
  END AS Quintile
FROM ranked
ORDER BY CAST(rnk AS REAL) / total, StudLastName