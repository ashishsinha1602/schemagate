WITH cust AS (
  SELECT o.customerid, SUM(od.unitprice * od.quantity) AS total
  FROM orders o
  JOIN order_details od ON od.orderid = o.orderid
  WHERE strftime('%Y', o.orderdate) = '1998'
  GROUP BY o.customerid
),
grouped AS (
  SELECT c.customerid, t.groupname
  FROM cust c
  JOIN customergroupthreshold t ON c.total BETWEEN t.rangebottom AND t.rangetop
)
SELECT groupname,
       COUNT(*) AS customer_count,
       100.0 * COUNT(*) / (SELECT COUNT(*) FROM cust) AS percentage
FROM grouped
GROUP BY groupname
ORDER BY groupname