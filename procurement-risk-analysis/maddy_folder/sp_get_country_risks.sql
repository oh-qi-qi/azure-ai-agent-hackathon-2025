CREATE OR ALTER PROCEDURE [dbo].[GetCountryRiskHeatmapData]
AS
BEGIN
    SET NOCOUNT ON;
    
    -- Temporary table to hold the flattened political risks
    DECLARE @PoliticalRisks TABLE (
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
    
    -- Insert the flattened political_risks data into the temporary table
    INSERT INTO @PoliticalRisks
    SELECT 
        JSON_VALUE(pr.value, '$.country') AS CountryName,
        JSON_VALUE(pr.value, '$.political_type') AS PoliticalType,
        JSON_VALUE(pr.value, '$.risk_information') AS RiskInformation,
        CAST(JSON_VALUE(pr.value, '$.likelihood') AS INT) AS Likelihood,
        JSON_VALUE(pr.value, '$.likelihood_reasoning') AS LikelihoodReasoning,
        JSON_VALUE(pr.value, '$.publication_date') AS PublicationDate,
        JSON_VALUE(pr.value, '$.citation_title') AS CitationTitle,
        JSON_VALUE(pr.value, '$.citation_name') AS CitationName,
        JSON_VALUE(pr.value, '$.citation_url') AS CitationUrl
    FROM [dbo].[dim_agent_thinking_log] AS dat
    CROSS APPLY OPENJSON(JSON_QUERY(dat.value, '$.political_risks')) AS pr
    WHERE dat.[action] = 'Political Risk JSON Data';
    
    -- Create table to hold country summary data
    DECLARE @CountrySummary TABLE (
        Country NVARCHAR(255),
        TotalLikelihood FLOAT,
        RiskCount INT
    );
    
    -- Calculate country totals
    INSERT INTO @CountrySummary
    SELECT 
        CountryName,
        SUM(CAST(Likelihood AS FLOAT)) AS TotalLikelihood,
        COUNT(*) AS RiskCount
    FROM @PoliticalRisks
    GROUP BY CountryName;
    
    -- Construct the final JSON result
    WITH CountryData AS (
        SELECT 
            cs.Country,
            ROUND(cs.TotalLikelihood / cs.RiskCount, 0) AS AverageRisk,
            (
                SELECT 
                    pr.CountryName AS 'country',
                    pr.PoliticalType AS 'description',
                    pr.RiskInformation AS 'summary',
                    pr.Likelihood AS 'likelihood',
                    pr.LikelihoodReasoning AS 'likelihood_reasoning',
                    pr.PublicationDate AS 'publication_date',
                    pr.CitationName AS 'source',
                    pr.CitationUrl AS 'source_url'
                FROM @PoliticalRisks pr
                WHERE pr.CountryName = cs.Country
                FOR JSON PATH
            ) AS Breakdown
        FROM @CountrySummary cs
    )
    
    SELECT (
        SELECT 
            CONVERT(NVARCHAR(30), GETDATE(), 126) AS 'DateTime_stamp',
            cd.Country,
            cd.AverageRisk AS 'Average_Risk',
            JSON_QUERY(cd.Breakdown) AS 'Breakdown'
        FROM CountryData cd
        FOR JSON PATH
    ) AS HeatmapData;
END