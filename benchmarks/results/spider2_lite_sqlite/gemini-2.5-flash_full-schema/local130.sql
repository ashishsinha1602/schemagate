WITH EnglishCourseGrades AS (
    SELECT
        ss.StudentID,
        s.StudLastName,
        ss.Grade
    FROM
        main.Student_Schedules AS ss
    JOIN
        main.Classes AS c ON ss.ClassID = c.ClassID
    JOIN
        main.Subjects AS sub ON c.SubjectID = sub.SubjectID
    JOIN
        main.Students AS s ON ss.StudentID = s.StudentID
    WHERE
        sub.SubjectName LIKE '%English%' AND ss.ClassStatus = 2
)
SELECT
    ecg.StudLastName,
    CASE
        WHEN CUME_DIST() OVER (ORDER BY ecg.Grade DESC) <= 0.2 THEN 'First'
        WHEN CUME_DIST() OVER (ORDER BY ecg.Grade DESC) <= 0.4 THEN 'Second'
        WHEN CUME_DIST() OVER (ORDER BY ecg.Grade DESC) <= 0.6 THEN 'Third'
        WHEN CUME_DIST() OVER (ORDER BY ecg.Grade DESC) <= 0.8 THEN 'Fourth'
        ELSE 'Fifth'
    END AS QuintileRank
FROM
    EnglishCourseGrades AS ecg
ORDER BY
    CASE
        WHEN CUME_DIST() OVER (ORDER BY ecg.Grade DESC) <= 0.2 THEN 1
        WHEN CUME_DIST() OVER (ORDER BY ecg.Grade DESC) <= 0.4 THEN 2
        WHEN CUME_DIST() OVER (ORDER BY ecg.Grade DESC) <= 0.6 THEN 3
        WHEN CUME_DIST() OVER (ORDER BY ecg.Grade DESC) <= 0.8 THEN 4
        ELSE 5
    END