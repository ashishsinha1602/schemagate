WITH CategoryPaymentCounts AS (
    SELECT
        op.product_category_name,
        oop.payment_type,
        COUNT(oop.order_id) AS num_payments
    FROM
        main.olist_order_items AS ooi
    JOIN
        main.olist_products AS op
        ON ooi.product_id = op.product_id
    JOIN
        main.olist_order_payments AS oop
        ON ooi.order_id = oop.order_id
    GROUP BY
        op.product_category_name,
        oop.payment_type
),
RankedCategoryPayments AS (
    SELECT
        product_category_name,
        payment_type,
        num_payments,
        ROW_NUMBER() OVER (PARTITION BY product_category_name ORDER BY num_payments DESC, payment_type ASC) AS rn
    FROM
        CategoryPaymentCounts
)
SELECT
    product_category_name,
    num_payments AS number_of_payments
FROM
    RankedCategoryPayments
WHERE
    rn = 1
ORDER BY
    num_payments DESC
LIMIT 3