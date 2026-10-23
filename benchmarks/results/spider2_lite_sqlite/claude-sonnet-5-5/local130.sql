WITH eng AS (
  SELECT s.StudLastName, ss.StudentID, ss.ClassID, ss.Grade
  FROM Student_Schedules ss
  JOIN Students s ON s.StudentID = ss.StudentID
  JOIN Classes c ON c.ClassID = ss.ClassID
  JOIN Subjects su ON su.SubjectID = c.SubjectID
  WHERE ss.ClassStatus = 2
    AND su.SubjectCode LIKE 'ENG%'
),
ranked AS (
  SELECT e.StudLastName, e.Grade,
    1.0 * (SELECT COUNT(*) FROM eng e2 WHERE e2.Grade >= e.Grade) / (SELECT COUNT(*) FROM eng) AS pct
  FROM eng e
)
SELECT StudLastName,
  CASE
    WHEN pct <= 0.2 THEN 'First'
    WHEN pct <= 0.4 THEN 'Second'
    WHEN pct <= 0.6 THEN 'Third'
    WHEN pct <= 0.8 THEN 'Fourth'
    ELSE 'Fifth'
  END AS Quintile
FROM ranked
ORDER BY pct, StudLastName