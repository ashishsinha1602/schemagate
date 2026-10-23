WITH PlayerCareerSpan AS (
    SELECT
        player_id,
        CAST(SUBSTR(debut, 1, 4) AS INTEGER) AS debut_year,
        CAST(SUBSTR(debut, 6, 2) AS INTEGER) AS debut_month,
        CAST(SUBSTR(debut, 9, 2) AS INTEGER) AS debut_day,
        CAST(SUBSTR(final_game, 1, 4) AS INTEGER) AS final_year,
        CAST(SUBSTR(final_game, 6, 2) AS INTEGER) AS final_month,
        CAST(SUBSTR(final_game, 9, 2) AS INTEGER) AS final_day
    FROM
        main.player
    WHERE
        debut IS NOT NULL AND final_game IS NOT NULL AND debut != '' AND final_game != ''
),
CalculatedSpans AS (
    SELECT
        player_id,
        ABS(final_year - debut_year) AS year_part,
        ROUND(ABS(final_month - debut_month) / 12.0, 2) AS month_part,
        ROUND(ABS(final_day - debut_day) / 365.0, 2) AS day_part
    FROM
        PlayerCareerSpan
)
SELECT
    AVG(year_part + month_part + day_part)
FROM
    CalculatedSpans