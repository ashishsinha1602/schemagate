WITH purchase_visits AS (
  SELECT DISTINCT visit_id
  FROM shopping_cart_events
  WHERE event_type = 3
)
SELECT
  h.page_name AS product,
  SUM(CASE WHEN e.event_type = 1 THEN 1 ELSE 0 END) AS views,
  SUM(CASE WHEN e.event_type = 2 THEN 1 ELSE 0 END) AS added_to_cart,
  SUM(CASE WHEN e.event_type = 2 AND pv.visit_id IS NULL THEN 1 ELSE 0 END) AS abandoned_in_cart,
  SUM(CASE WHEN e.event_type = 2 AND pv.visit_id IS NOT NULL THEN 1 ELSE 0 END) AS purchases
FROM shopping_cart_events e
JOIN shopping_cart_page_hierarchy h ON e.page_id = h.page_id
LEFT JOIN purchase_visits pv ON pv.visit_id = e.visit_id
WHERE h.page_id NOT IN (1, 2, 12, 13)
GROUP BY h.page_id, h.page_name
ORDER BY h.page_id