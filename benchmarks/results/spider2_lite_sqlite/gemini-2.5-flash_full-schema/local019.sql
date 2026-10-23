WITH ParsedMatches AS (
    SELECT
        winner_id,
        loser_id,
        title_id,
        duration,
        CASE
            WHEN duration IS NULL OR duration = '' OR INSTR(duration, ':') = 0 THEN NULL
            ELSE
                CAST(SUBSTR(duration, 1, INSTR(duration, ':') - 1) AS INTEGER) * 60 +
                CAST(SUBSTR(duration, INSTR(duration, ':') + 1) AS INTEGER)
        END AS duration_seconds
    FROM main.Matches
    WHERE
        title_id LIKE '%NXT%' AND
        (title_change IS NULL OR title_change = 0) AND
        duration IS NOT NULL AND duration != '' AND INSTR(duration, ':') > 0
)
SELECT
    winner_id,
    loser_id
FROM ParsedMatches
WHERE
    duration_seconds = (SELECT MIN(duration_seconds) FROM ParsedMatches WHERE duration_seconds IS NOT NULL)