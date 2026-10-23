WITH EntertainerAllStyles AS (
    SELECT
        es.EntertainerID,
        es.StyleID,
        es.StyleStrength,
        ROW_NUMBER() OVER (PARTITION BY es.EntertainerID ORDER BY es.StyleStrength DESC) AS rnk,
        COUNT(es.StyleID) OVER (PARTITION BY es.EntertainerID) AS TotalStylesCount
    FROM
        main.Entertainer_Styles AS es
),
EntertainerFilteredStyles AS (
    SELECT
        EntertainerID,
        MAX(CASE WHEN rnk = 1 THEN StyleID END) AS Style1ID,
        MAX(CASE WHEN rnk = 2 THEN StyleID END) AS Style2ID,
        MAX(TotalStylesCount) AS TotalStyles
    FROM
        EntertainerAllStyles
    WHERE
        rnk <= 2
    GROUP BY
        EntertainerID
    HAVING
        TotalStyles BETWEEN 2 AND 3
),
CustomerAllPreferences AS (
    SELECT
        mp.CustomerID,
        mp.StyleID,
        mp.PreferenceSeq,
        ROW_NUMBER() OVER (PARTITION BY mp.CustomerID ORDER BY mp.PreferenceSeq ASC) AS rnk,
        COUNT(mp.StyleID) OVER (PARTITION BY mp.CustomerID) AS TotalPreferencesCount
    FROM
        main.Musical_Preferences AS mp
),
CustomerFilteredPreferences AS (
    SELECT
        CustomerID,
        MAX(CASE WHEN rnk = 1 THEN StyleID END) AS Pref1ID,
        MAX(CASE WHEN rnk = 2 THEN StyleID END) AS Pref2ID,
        MAX(TotalPreferencesCount) AS TotalPreferences
    FROM
        CustomerAllPreferences
    WHERE
        rnk <= 2
    GROUP BY
        CustomerID
    HAVING
        TotalPreferences BETWEEN 2 AND 3
)
SELECT
    e.EntStageName,
    c.CustLastName
FROM
    main.Entertainers AS e
JOIN
    EntertainerFilteredStyles AS ets
    ON e.EntertainerID = ets.EntertainerID
JOIN
    main.Customers AS c
JOIN
    CustomerFilteredPreferences AS ctp
    ON c.CustomerID = ctp.CustomerID
WHERE
    (
        (ets.Style1ID = ctp.Pref1ID AND ets.Style2ID = ctp.Pref2ID)
        OR
        (ets.Style1ID = ctp.Pref2ID AND ets.Style2ID = ctp.Pref1ID)
    )