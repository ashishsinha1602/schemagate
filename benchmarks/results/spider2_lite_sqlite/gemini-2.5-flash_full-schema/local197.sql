WITH top_10_customers AS (
    SELECT
        c.customer_id,
        c.first_name,
        c.last_name
    FROM
        main.customer AS c
    JOIN
        main.payment AS p ON c.customer_id = p.customer_id
    GROUP BY
        c.customer_id, c.first_name, c.last_name
    ORDER BY
        SUM(p.amount) DESC
    LIMIT 10
),
monthly_payments AS (
    SELECT
        t10.customer_id,
        t10.first_name,
        t10.last_name,
        STRFTIME('%Y-%m', p.payment_date) AS payment_month,
        SUM(p.amount) AS monthly_total
    FROM
        main.payment AS p
    JOIN
        top_10_customers AS t10 ON p.customer_id = t10.customer_id
    GROUP BY
        t10.customer_id, t10.first_name, t10.last_name, payment_month
),
monthly_diffs AS (
    SELECT
        customer_id,
        first_name,
        last_name,
        payment_month,
        monthly_total,
        LAG(monthly_total, 1) OVER (PARTITION BY customer_id ORDER BY payment_month) AS previous_month_total,
        monthly_total - LAG(monthly_total, 1) OVER (PARTITION BY customer_id ORDER BY payment_month) AS month_over_month_change
    FROM
        monthly_payments
)
SELECT
    md.first_name,
    md.last_name,
    md.payment_month,
    ROUND(md.month_over_month_change, 2)
FROM
    monthly_diffs AS md
WHERE
    md.previous_month_total IS NOT NULL
ORDER BY
    ABS(md.month_over_month_change) DESC
LIMIT 1