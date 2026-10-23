WITH AnnualDeliveredOrders AS (
    SELECT
        STRFTIME('%Y', order_purchase_timestamp) AS order_year,
        COUNT(order_id) AS delivered_orders_count
    FROM
        main.olist_orders
    WHERE
        order_status = 'delivered'
        AND STRFTIME('%Y', order_purchase_timestamp) IN ('2016', '2017', '2018')
    GROUP BY
        order_year
),
LowestAnnualVolumeYear AS (
    SELECT
        order_year
    FROM
        AnnualDeliveredOrders
    ORDER BY
        delivered_orders_count ASC
    LIMIT 1
),
MonthlyDeliveredOrdersInLowestYear AS (
    SELECT
        STRFTIME('%Y-%m', o.order_purchase_timestamp) AS order_month,
        COUNT(o.order_id) AS monthly_delivered_orders_count
    FROM
        main.olist_orders AS o
    JOIN
        LowestAnnualVolumeYear AS lay ON STRFTIME('%Y', o.order_purchase_timestamp) = lay.order_year
    WHERE
        o.order_status = 'delivered'
    GROUP BY
        order_month
)
SELECT
    MAX(monthly_delivered_orders_count)
FROM
    MonthlyDeliveredOrdersInLowestYear