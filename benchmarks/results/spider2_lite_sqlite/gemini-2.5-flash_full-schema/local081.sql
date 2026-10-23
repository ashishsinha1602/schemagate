WITH CustomerSpending1998 AS (
  SELECT
    o.customerid,
    SUM(od.unitprice * od.quantity) AS total_spent
  FROM main.orders AS o
  JOIN main.order_details AS od
    ON o.orderid = od.orderid
  WHERE
    STRFTIME('%Y', o.orderdate) = '1998'
  GROUP BY
    o.customerid
), CustomersWithGroups AS (
  SELECT
    cs.customerid,
    cgt.groupname
  FROM CustomerSpending1998 AS cs
  JOIN main.customergroupthreshold AS cgt
    ON cs.total_spent >= cgt.rangebottom AND cs.total_spent <= cgt.rangetop
), GroupCounts AS (
  SELECT
    groupname,
    COUNT(customerid) AS customer_count
  FROM CustomersWithGroups
  GROUP BY
    groupname
)
SELECT
  gc.groupname,
  gc.customer_count,
  CAST(gc.customer_count AS REAL) * 100 / (
    SELECT
      COUNT(customerid)
    FROM CustomerSpending1998
  ) AS percentage_of_total_customers
FROM GroupCounts AS gc
ORDER BY
  gc.groupname