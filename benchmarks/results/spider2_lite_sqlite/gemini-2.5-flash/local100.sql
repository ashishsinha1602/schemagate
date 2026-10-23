WITH ShahrukhKhan AS (
    SELECT PID
    FROM Person
    WHERE Name = 'Shahrukh Khan'
),
SK_Movies AS (
    -- Movies Shahrukh Khan acted in
    SELECT MID
    FROM M_Cast
    WHERE PID = (SELECT PID FROM ShahrukhKhan)
),
SN1_Actors AS (
    -- Actors who acted in a movie with Shahrukh Khan (Shahrukh Number 1)
    SELECT DISTINCT MC.PID
    FROM M_Cast AS MC
    WHERE MC.MID IN (SELECT MID FROM SK_Movies)
      AND MC.PID != (SELECT PID FROM ShahrukhKhan)
),
SN1_Actor_Movies AS (
    -- Movies where Shahrukh Number 1 actors acted
    SELECT DISTINCT MC.MID
    FROM M_Cast AS MC
    WHERE MC.PID IN (SELECT PID FROM SN1_Actors)
),
Potential_SN2_Actors AS (
    -- Actors who acted in movies with Shahrukh Number 1 actors
    SELECT DISTINCT MC.PID
    FROM M_Cast AS MC
    WHERE MC.MID IN (SELECT MID FROM SN1_Actor_Movies)
)
-- Count actors who are in Potential_SN2_Actors but are neither Shahrukh Khan
-- nor Shahrukh Number 1 actors.
SELECT COUNT(DISTINCT P.PID)
FROM Potential_SN2_Actors AS P
WHERE P.PID != (SELECT PID FROM ShahrukhKhan)
  AND P.PID NOT IN (SELECT PID FROM SN1_Actors)