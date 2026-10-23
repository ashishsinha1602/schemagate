WITH ProductFirstPick AS (
  SELECT
    pl.product_id,
    pl.qty,
    ROW_NUMBER() OVER (PARTITION BY pl.product_id ORDER BY pgl.log_time, pl.line_no) AS rn
  FROM main.picking_line AS pl
  JOIN main.picking_log AS pgl
    ON pl.picklist_id = pgl.picklist_id AND pl.line_no = pgl.pickline_no
  WHERE
    pl.order_id = 421
)
SELECT
  p.name AS product_name,
  AVG(pfp.qty) AS average_picked_qty
FROM ProductFirstPick AS pfp
JOIN main.products AS p
  ON pfp.product_id = p.id
WHERE
  pfp.rn = 1
GROUP BY
  p.name,
  pfp.product_id