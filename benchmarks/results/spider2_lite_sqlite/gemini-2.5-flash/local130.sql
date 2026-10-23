WITH EnglishCourseGrades AS (
    SELECT
        ss.StudentID,
        s.StudLastName,
        ss.Grade
    FROM
        main.Student_Schedules AS ss
    JOIN
        main.Classes AS c
        ON ss.ClassID = c.ClassID
    JOIN
        main.Subjects AS sub
        ON c.SubjectID = sub.SubjectID
    JOIN
        main.Students AS s
        ON ss.StudentID = s.StudentID
    WHERE
        ss.ClassStatus = 2 -- Completed courses
        AND sub.SubjectName LIKE '%English%'
),
RankedGrades AS (
    SELECT
        StudentID,
        StudLastName,
        Grade,
        RANK() OVER (ORDER BY Grade DESC) AS GradeRank,
        COUNT(*) OVER () AS TotalEntries
    FROM
        EnglishCourseGrades
)
SELECT
    rg.StudLastName,
    CASE
        WHEN CAST(rg.GradeRank AS REAL) / rg.TotalEntries <= 0.20 THEN 'First'
        WHEN CAST(rg.GradeRank AS REAL) / rg.TotalEntries <= 0.40 THEN 'Second'
        WHEN CAST(rg.GradeRank AS REAL) / rg.TotalEntries <= 0.60 THEN 'Third'
        WHEN CAST(rg.GradeRank AS REAL) / rg.TotalEntries <= 0.80 THEN 'Fourth'
        ELSE 'Fifth'
    END AS QuintileRank
FROM
    RankedGrades AS rg
ORDER BY
    CASE QuintileRank
        WHEN 'First' THEN 1
        WHEN 'Second' THEN 2
        WHEN 'Third' THEN 3
        WHEN 'Fourth' THEN 4
        WHEN 'Fifth' THEN 5
    END