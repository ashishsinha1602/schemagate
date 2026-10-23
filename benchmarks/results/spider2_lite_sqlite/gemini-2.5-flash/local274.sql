SELECT
  T1.name,
  AVG(T2.qty)
FROM main.products AS T1
INNER JOIN main.picking_line AS T2
  ON T1.id = T2.product_id
WHERE
  T1.id IN (
    SELECT DISTINCT
      T3.product_id
    FROM main.picking_line AS T3
    WHERE
      T3.order_id = 421
  )
GROUP BY
  T1.name