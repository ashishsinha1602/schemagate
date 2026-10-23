WITH CustomerSpending1998 AS (
    SELECT
        o.customerid,
        SUM(od.unitprice * od.quantity) AS total_spent
    FROM
        main.orders AS o
    JOIN
        main.order_details AS od
        ON o.orderid = od.orderid
    WHERE
        strftime('%Y', o.orderdate) = '1998'
    GROUP BY
        o.customerid
),
CustomerGroupAssignment AS (
    SELECT
        cs.customerid,
        cgt.groupname
    FROM
        CustomerSpending1998 AS cs
    JOIN
        main.customergroupthreshold AS cgt
        ON cs.total_spent >= cgt.rangebottom AND cs.total_spent <= cgt.rangetop
),
GroupCounts AS (
    SELECT
        cga.groupname,
        COUNT(cga.customerid) AS customer_count
    FROM
        CustomerGroupAssignment AS cga
    GROUP BY
        cga.groupname
)
SELECT
    gc.groupname,
    gc.customer_count,
    CAST(gc.customer_count AS REAL) * 100 / (SELECT COUNT(DISTINCT customerid) FROM CustomerSpending1998) AS percentage
FROM
    GroupCounts AS gc
ORDER BY
    gc.groupname