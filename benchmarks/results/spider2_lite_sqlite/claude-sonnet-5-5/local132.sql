SELECT DISTINCT e.EntStageName, c.CustLastName
FROM Entertainers e
JOIN Entertainer_Styles es1 ON es1.EntertainerID = e.EntertainerID AND es1.StyleStrength = 1
JOIN Entertainer_Styles es2 ON es2.EntertainerID = e.EntertainerID AND es2.StyleStrength = 2
JOIN Musical_Preferences p1 ON p1.PreferenceSeq = 1
JOIN Musical_Preferences p2 ON p2.CustomerID = p1.CustomerID AND p2.PreferenceSeq = 2
JOIN Customers c ON c.CustomerID = p1.CustomerID
WHERE ((es1.StyleID = p1.StyleID AND es2.StyleID = p2.StyleID)
    OR (es1.StyleID = p2.StyleID AND es2.StyleID = p1.StyleID))
  AND e.EntertainerID IN (SELECT EntertainerID FROM Entertainer_Styles GROUP BY EntertainerID HAVING COUNT(*) <= 3)
  AND c.CustomerID IN (SELECT CustomerID FROM Musical_Preferences GROUP BY CustomerID HAVING COUNT(*) <= 3)