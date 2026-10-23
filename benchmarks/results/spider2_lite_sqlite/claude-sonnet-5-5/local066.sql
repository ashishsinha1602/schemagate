SELECT t.topping_name AS name,
       SUM(
         CASE WHEN (',' || replace(r.toppings,' ','') || ',') LIKE '%,' || t.topping_id || ',%'
                   AND (',' || replace(coalesce(o.exclusions,''),' ','') || ',') NOT LIKE '%,' || t.topping_id || ',%'
              THEN 1 ELSE 0 END
         +
         CASE WHEN (',' || replace(coalesce(o.extras,''),' ','') || ',') LIKE '%,' || t.topping_id || ',%'
              THEN 1 ELSE 0 END
       ) AS quantity
FROM pizza_clean_customer_orders o
JOIN pizza_clean_runner_orders ro ON ro.order_id = o.order_id
JOIN pizza_recipes r ON r.pizza_id = o.pizza_id
CROSS JOIN pizza_toppings t
WHERE (ro.cancellation IS NULL OR trim(ro.cancellation) = '' OR lower(ro.cancellation) = 'null')
GROUP BY t.topping_id, t.topping_name
HAVING quantity > 0
ORDER BY quantity DESC, name