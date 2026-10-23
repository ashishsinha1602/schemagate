WITH CustomerOrderPayments AS (
    SELECT
        o.customer_id,
        o.order_id,
        SUM(op.payment_value) AS total_order_payment
    FROM
        main.orders AS o
    JOIN
        main.order_payments AS op
        ON o.order_id = op.order_id
    GROUP BY
        o.customer_id,
        o.order_id
),
CustomerAvgPayment AS (
    SELECT
        cop.customer_id,
        AVG(cop.total_order_payment) AS avg_payment_per_order
    FROM
        CustomerOrderPayments AS cop
    GROUP BY
        cop.customer_id
    ORDER BY
        avg_payment_per_order DESC
    LIMIT 3
),
CustomerOrderCounts AS (
    SELECT
        o.customer_id,
        COUNT(o.order_id) AS number_of_orders
    FROM
        main.orders AS o
    WHERE o.customer_id IN (SELECT customer_id FROM CustomerAvgPayment)
    GROUP BY
        o.customer_id
),
CustomerLifespan AS (
    SELECT
        o.customer_id,
        MIN(o.order_purchase_timestamp) AS first_purchase_date,
        MAX(o.order_purchase_timestamp) AS last_purchase_date
    FROM
        main.orders AS o
    WHERE o.customer_id IN (SELECT customer_id FROM CustomerAvgPayment)
    GROUP BY
        o.customer_id
)
SELECT
    cap.customer_id,
    coc.number_of_orders,
    cap.avg_payment_per_order,
    CASE
        WHEN (julianday(cl.last_purchase_date) - julianday(cl.first_purchase_date)) < 7
        THEN 1.0
        ELSE (julianday(cl.last_purchase_date) - julianday(cl.first_purchase_date)) / 7.0
    END AS customer_lifespan_weeks
FROM
    CustomerAvgPayment AS cap
JOIN
    CustomerOrderCounts AS coc
    ON cap.customer_id = coc.customer_id
JOIN
    CustomerLifespan AS cl
    ON cap.customer_id = cl.customer_id
ORDER BY
    cap.avg_payment_per_order DESC