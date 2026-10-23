WITH ShahrukhKhan AS (
  SELECT PID
  FROM Person
  WHERE Name = 'Shahrukh Khan'
),
SK_PID_Val AS (
  SELECT PID FROM ShahrukhKhan
),
SK_1_Actors AS (
  -- Actors who acted directly with Shahrukh Khan
  SELECT DISTINCT MC.PID
  FROM M_Cast AS MC
  WHERE MC.MID IN (
    SELECT MID
    FROM M_Cast
    WHERE PID = (SELECT PID FROM SK_PID_Val)
  )
  AND MC.PID != (SELECT PID FROM SK_PID_Val)
),
SK_1_Actor_Movies AS (
  -- All movies where any SK_1_Actor acted
  SELECT DISTINCT MID
  FROM M_Cast
  WHERE PID IN (SELECT PID FROM SK_1_Actors)
),
Potential_SK_2_Actors AS (
  -- All actors who acted in movies with SK_1_Actors
  SELECT DISTINCT PID
  FROM M_Cast
  WHERE MID IN (SELECT MID FROM SK_1_Actor_Movies)
)
SELECT COUNT(DISTINCT PSA.PID)
FROM Potential_SK_2_Actors AS PSA
WHERE PSA.PID != (SELECT PID FROM SK_PID_Val)
  AND PSA.PID NOT IN (SELECT PID FROM SK_1_Actors)