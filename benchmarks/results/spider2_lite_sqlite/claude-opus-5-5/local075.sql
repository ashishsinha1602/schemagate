WITH purchase_visits AS (
  SELECT DISTINCT visit_id
  FROM shopping_cart_events
  WHERE event_type = 3
),
product_events AS (
  SELECT e.visit_id, h.page_id, h.page_name, h.product_id, e.event_type,
         CASE WHEN pv.visit_id IS NOT NULL THEN 1 ELSE 0 END AS visit_purchased
  FROM shopping_cart_events e
  JOIN shopping_cart_page_hierarchy h ON e.page_id = h.page_id
  LEFT JOIN purchase_visits pv ON pv.visit_id = e.visit_id
  WHERE h.page_id NOT IN (1, 2, 12, 13)
)
SELECT page_id,
       page_name,
       product_id,
       SUM(CASE WHEN event_type = 1 THEN 1 ELSE 0 END) AS views,
       SUM(CASE WHEN event_type = 2 THEN 1 ELSE 0 END) AS added_to_cart,
       SUM(CASE WHEN event_type = 2 AND visit_purchased = 0 THEN 1 ELSE 0 END) AS left_in_cart,
       SUM(CASE WHEN event_type = 2 AND visit_purchased = 1 THEN 1 ELSE 0 END) AS purchases
FROM product_events
GROUP BY page_id, page_name, product_id
ORDER BY page_id