WITH ent AS (
  SELECT EntertainerID,
         MAX(CASE WHEN rn = 1 THEN StyleID END) AS s1,
         MAX(CASE WHEN rn = 2 THEN StyleID END) AS s2
  FROM (
    SELECT EntertainerID, StyleID,
           ROW_NUMBER() OVER (PARTITION BY EntertainerID ORDER BY StyleStrength) AS rn,
           COUNT(*) OVER (PARTITION BY EntertainerID) AS cnt
    FROM Entertainer_Styles
  ) t
  WHERE cnt <= 3
  GROUP BY EntertainerID
),
cust AS (
  SELECT CustomerID,
         MAX(CASE WHEN rn = 1 THEN StyleID END) AS p1,
         MAX(CASE WHEN rn = 2 THEN StyleID END) AS p2
  FROM (
    SELECT CustomerID, StyleID,
           ROW_NUMBER() OVER (PARTITION BY CustomerID ORDER BY PreferenceSeq) AS rn,
           COUNT(*) OVER (PARTITION BY CustomerID) AS cnt
    FROM Musical_Preferences
  ) t
  WHERE cnt <= 3
  GROUP BY CustomerID
)
SELECT e.EntStageName, c.CustLastName
FROM ent
JOIN cust
  ON (cust.p1 = ent.s1 AND cust.p2 = ent.s2)
  OR (cust.p1 = ent.s2 AND cust.p2 = ent.s1)
JOIN Entertainers e ON e.EntertainerID = ent.EntertainerID
JOIN Customers c ON c.CustomerID = cust.CustomerID