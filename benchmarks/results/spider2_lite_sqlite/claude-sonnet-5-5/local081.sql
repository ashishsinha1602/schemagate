WITH cust_totals AS (
  SELECT o.customerid, SUM(od.unitprice * od.quantity) AS total
  FROM orders o
  JOIN order_details od ON od.orderid = o.orderid
  WHERE strftime('%Y', o.orderdate) = '1998'
  GROUP BY o.customerid
),
grouped AS (
  SELECT c.customerid, c.total, g.groupname
  FROM cust_totals c
  JOIN customergroupthreshold g ON c.total >= g.rangebottom AND c.total < g.rangetop
)
SELECT groupname,
       COUNT(*) AS customer_count,
       COUNT(*) * 100.0 / (SELECT COUNT(*) FROM cust_totals) AS percentage
FROM grouped
GROUP BY groupname