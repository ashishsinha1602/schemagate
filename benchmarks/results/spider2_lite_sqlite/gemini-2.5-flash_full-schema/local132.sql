WITH RankedEntertainerStyles AS (
    SELECT
        es.EntertainerID,
        es.StyleID,
        ROW_NUMBER() OVER (PARTITION BY es.EntertainerID ORDER BY es.StyleStrength DESC) AS rn
    FROM
        main.Entertainer_Styles AS es
),
RankedCustomerPreferences AS (
    SELECT
        mp.CustomerID,
        mp.StyleID,
        ROW_NUMBER() OVER (PARTITION BY mp.CustomerID ORDER BY mp.PreferenceSeq ASC) AS rn
    FROM
        main.Musical_Preferences AS mp
)
SELECT DISTINCT
    e.EntStageName,
    c.CustLastName
FROM
    main.Entertainers AS e
JOIN
    RankedEntertainerStyles AS res1 ON e.EntertainerID = res1.EntertainerID AND res1.rn = 1
JOIN
    RankedEntertainerStyles AS res2 ON e.EntertainerID = res2.EntertainerID AND res2.rn = 2
JOIN
    main.Customers AS c
JOIN
    RankedCustomerPreferences AS rcp1 ON c.CustomerID = rcp1.CustomerID AND rcp1.rn = 1
JOIN
    RankedCustomerPreferences AS rcp2 ON c.CustomerID = rcp2.CustomerID AND rcp2.rn = 2
WHERE
    (
        (rcp1.StyleID = res1.StyleID AND rcp2.StyleID = res2.StyleID)
        OR
        (rcp1.StyleID = res2.StyleID AND rcp2.StyleID = res1.StyleID)
    )