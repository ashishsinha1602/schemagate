WITH Top10Customers AS (
    SELECT
        c.customer_id
    FROM
        main.customer AS c
    JOIN
        main.payment AS p ON c.customer_id = p.customer_id
    GROUP BY
        c.customer_id
    ORDER BY
        SUM(p.amount) DESC
    LIMIT 10
),
MonthlyPayments AS (
    SELECT
        p.customer_id,
        STRFTIME('%Y-%m', p.payment_date) AS payment_month,
        SUM(p.amount) AS monthly_total
    FROM
        main.payment AS p
    WHERE
        p.customer_id IN (SELECT customer_id FROM Top10Customers)
    GROUP BY
        p.customer_id,
        payment_month
),
MonthlyChanges AS (
    SELECT
        customer_id,
        payment_month,
        monthly_total,
        LAG(monthly_total, 1) OVER (PARTITION BY customer_id ORDER BY payment_month) AS previous_month_total
    FROM
        MonthlyPayments
)
SELECT
    customer_id,
    payment_month,
    ROUND(monthly_total - previous_month_total, 2) AS month_over_month_change
FROM
    MonthlyChanges
WHERE
    previous_month_total IS NOT NULL
ORDER BY
    ABS(monthly_total - previous_month_total) DESC
LIMIT 1