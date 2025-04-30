CREATE OR ALTER PROCEDURE [dbo].[GetCountryRiskHeatmapData]
    @ConversationId NVARCHAR(255) = NULL,
    @SessionId NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @PoliticalRisks TABLE (
        ConversationId NVARCHAR(255),
        SessionId NVARCHAR(255),
        CountryName NVARCHAR(255),
        PoliticalType NVARCHAR(255),
        RiskInformation NVARCHAR(MAX),
        Likelihood INT,
        LikelihoodReasoning NVARCHAR(MAX),
        PublicationDate NVARCHAR(100),
        CitationTitle NVARCHAR(255),
        CitationName NVARCHAR(255),
        CitationUrl NVARCHAR(255)
    );

    -- Insert only when political_risks is not null
    -- Extract and normalize political risks
    INSERT INTO @PoliticalRisks
    SELECT 
        dat.conversation_id,
        dat.session_id,
        TRIM(value_split.CountryName),  -- use split value here
        JSON_VALUE(pr.value, '$.political_type'),
        JSON_VALUE(pr.value, '$.risk_information'),
        TRY_CAST(JSON_VALUE(pr.value, '$.likelihood') AS INT),
        JSON_VALUE(pr.value, '$.likelihood_reasoning'),
        JSON_VALUE(pr.value, '$.publication_date'),
        JSON_VALUE(pr.value, '$.citation_title'),
        JSON_VALUE(pr.value, '$.citation_name'),
        JSON_VALUE(pr.value, '$.citation_url')
    FROM [dbo].[dim_agent_event_log] AS dat
    CROSS APPLY (
        SELECT JSON_QUERY(dat.agent_output, '$.political_risks') AS risks
    ) AS filtered
    CROSS APPLY OPENJSON(filtered.risks) AS pr
    OUTER APPLY (
        -- Split country field by '-' and return each as a row
        SELECT 
            value AS CountryName
        FROM STRING_SPLIT(
            JSON_VALUE(pr.value, '$.country'),
            '-'
        )
    ) AS value_split
    WHERE dat.[action] = 'Political Risk JSON Data'
    AND JSON_QUERY(dat.agent_output, '$.political_risks') IS NOT NULL
    AND (@ConversationId IS NULL OR dat.conversation_id = @ConversationId)
    AND (@SessionId IS NULL OR dat.session_id = @SessionId);

    DECLARE @CountrySummary TABLE (
        ConversationId NVARCHAR(255),
        SessionId NVARCHAR(255),
        Country NVARCHAR(255),
        TotalLikelihood FLOAT,
        RiskCount INT
    );

    INSERT INTO @CountrySummary
    SELECT 
        ConversationId,
        SessionId,
        CountryName,
        SUM(CAST(Likelihood AS FLOAT)),
        COUNT(*)
    FROM @PoliticalRisks
    GROUP BY ConversationId, SessionId, CountryName;

    WITH CountryData AS (
        SELECT 
            cs.ConversationId,
            cs.SessionId,
            cs.Country,
            ROUND(cs.TotalLikelihood / NULLIF(cs.RiskCount, 0), 0) AS AverageRisk,
            (
                SELECT 
                    pr.CountryName AS country,
                    pr.PoliticalType AS description,
                    pr.RiskInformation AS summary,
                    pr.Likelihood AS likelihood,
                    pr.LikelihoodReasoning AS likelihood_reasoning,
                    pr.PublicationDate AS publication_date,
                    pr.CitationName AS source,
                    pr.CitationUrl AS source_url
                FROM @PoliticalRisks pr
                WHERE pr.CountryName = cs.Country
                  AND pr.ConversationId = cs.ConversationId
                  AND pr.SessionId = cs.SessionId
                FOR JSON PATH
            ) AS Breakdown
        FROM @CountrySummary cs
    )

    SELECT
        CONVERT(NVARCHAR(30), GETDATE(), 126) AS DateTime_stamp,
        cd.ConversationId,
        cd.SessionId,
        cd.Country,
        cd.AverageRisk AS Average_Risk,
        JSON_QUERY(cd.Breakdown) AS Breakdown
    FROM CountryData cd;
END
