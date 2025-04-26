import json
#import pyodbc
import datetime
from semantic_kernel.functions.kernel_function_decorator import kernel_function

class VisualPlugin:
    """A plugin for converting the risk analyst agent outputs into inputs for the heatmap
    and report."""
    
    def __init__(self, connection_string):
        self.connection_string = connection_string
    
    @kernel_function(description="Converts political news from agent output to structured risk JSON format")
    def convert_political_news_to_risk_json(self, news_articles_json: str) -> str:
        """Converts a JSON array of political news articles into a structured risk JSON format
        
        Expected input is a JSON array of news articles with information about political events
        that may affect supply chains. The function will convert this into a standardized risk format.
        
        Each news article in the input should contain:
        - country: country the news is about
        - risk_category: "Political"
        - summary: summary of the news article
        - likelihood: risk rating (0-5)
        - likelihood_reasoning: explanation for the risk rating
        - description: type of political change (elections, strikes, etc.)
        - publication_date: date of the news article
        - source: publisher of the news article
        - source_url: URL link to the original article

        Example Input -> news_articles_json:
        [
            {
                "country": "United Kingdom",
                "risk_category": "Political",
                "summary": "Parliament considering new trade regulations affecting EU imports",
                "likelihood": 3,
                "likelihood_reasoning": "The bill has strong support but faces opposition from key industry groups",
                "description": "trade regulation",
                "publication_date": "2025-04-10",
                "source": "Financial Times",
                "source_url": "https://www.ft.com/content/example-article-1"
            },
            {
                "country": "Brazil",
                "risk_category": "Political",
                "summary": "Nationwide trucker strike disrupting supply chains across major ports",
                "likelihood": 4,
                "likelihood_reasoning": "Strike has lasted 5 days with no resolution in sight",
                "description": "labor strike",
                "publication_date": "2025-04-15",
                "source": "Reuters",
                "source_url": "https://www.reuters.com/article/example-article-2"
            },
        ]
        
        Returns a JSON string with a standardized risk format:
        {
            "risks": [
                {article1 data},
                {article2 data},
                ...
            ]
        }
        """
        try:
            # Parse the input JSON array
            news_articles = json.loads(news_articles_json)
            
            # Initialize the result structure
            political_risks = {
                "risk_category": "Political",
                "risks": []
            }
            
            # Process each news article
            for article in news_articles:
                try:
                    # Validate required fields
                    required_fields = [
                        'country', 'summary', 'likelihood', 'likelihood_reasoning',
                        'description', 'publication_date', 'source', 'source_url'
                    ]
                    
                    for field in required_fields:
                        if field not in article:
                            raise ValueError(f"Missing required field: {field}")
                    
                    # Ensure likelihood is a number between 0-5
                    likelihood = article['likelihood']
                    if not isinstance(likelihood, (int, float)) or likelihood < 0 or likelihood > 5:
                        raise ValueError(f"Likelihood must be a number between 0-5, got: {likelihood}")
                    
                    # Add the validated article to the risks array
                    political_risks["risks"].append({
                        "country": article["country"],
                        "summary": article["summary"],
                        "likelihood": article["likelihood"],
                        "likelihood_reasoning": article["likelihood_reasoning"],
                        "description": article["description"],
                        "publication_date": article["publication_date"],
                        "source": article["source"],
                        "source_url": article["source_url"]
                    })
                    
                except Exception as article_error:
                    # Log the error but continue processing other articles
                    print(f"Error processing article: {str(article_error)}")
                    continue
            
            # Return the formatted JSON result
            return json.dumps(political_risks, indent=2)
        
        except Exception as e:
            return json.dumps({"error": f"Failed to process political news: {str(e)}"})


    @kernel_function(description="Merges risk data from multiple agents into a unified risk array")
    def merge_agent_risk_outputs(self, political_news_json: str, tariff_news_json: str, logistics_news_json: str) -> str:
        """Merges risk data from three different agents into a unified risk array
        
        Takes JSON arrays from three different agents (political, tariff, logistics),
        validates the data, and merges them into a single unified array of risk objects.
        
        Each agent's input should be a JSON array of news articles where each article contains:
        - country: country the news is about
        - risk_category: category of risk ("Political", "Tariffs", "Logistics")
        - summary: summary of the news article
        - likelihood: risk rating (0-5)
        - likelihood_reasoning: explanation for the risk rating
        - description: type of political change (elections, strikes, etc.)
        - publication_date: date of the news article
        - source: publisher of the news article
        - source_url: URL link to the original article
        
        Returns a JSON string with a single array containing all validated risk objects
        from all three agents.
        """
        try:
            # Initialize the result array
            all_risks = []
            
            # Define a function to process each agent's data
            def process_agent_data(news_json, default_category):
                try:
                    # Parse the JSON string
                    news_articles = json.loads(news_json)
                    
                    # Process each article
                    for article in news_articles:
                        try:
                            # Validate required fields
                            required_fields = [
                                'country', 'summary', 'likelihood', 'likelihood_reasoning',
                                'description', 'publication_date', 'source', 'source_url'
                            ]
                            
                            for field in required_fields:
                                if field not in article:
                                    raise ValueError(f"Missing required field: {field}")
                            
                            # Ensure likelihood is a number between 0-5
                            likelihood = article['likelihood']
                            if not isinstance(likelihood, (int, float)) or likelihood < 0 or likelihood > 5:
                                raise ValueError(f"Likelihood must be a number between 0-5, got: {likelihood}")
                            
                            # Add risk_category if not present
                            if 'risk_category' not in article:
                                article['risk_category'] = default_category
                            
                            # Add the validated article to the results array
                            all_risks.append(article)
                            
                        except Exception as article_error:
                            # Log the error but continue processing other articles
                            print(f"Error processing article: {str(article_error)}")
                            continue
                            
                except Exception as agent_error:
                    print(f"Error processing agent data: {str(agent_error)}")
                    # Continue with other agents even if one fails
            
            # Process data from each agent
            process_agent_data(political_news_json, "Political")
            process_agent_data(tariff_news_json, "Tariffs")
            process_agent_data(logistics_news_json, "Logistics")
            
            # Sort the combined results by country and then by likelihood (highest first)
            sorted_risks = sorted(
                all_risks, 
                key=lambda x: (x.get("country", ""), -x.get("likelihood", 0))
            )
            
            # Return the formatted JSON result
            return json.dumps(sorted_risks, indent=2)
        
        except Exception as e:
            return json.dumps({"error": f"Failed to merge agent outputs: {str(e)}"})    

    @kernel_function(description="Creates country-specific risk heatmap data with averages and breakdowns")
    def create_country_risk_heatmap(self, news_articles_json: str) -> str:
        """Creates a heatmap-ready JSON structure with country risk averages and detailed breakdowns
        
        Takes a JSON array of news articles and aggregates them by country, calculating
        average risk scores and providing the full breakdown of risks for each country.
        
        Expected input is a JSON array of news articles where each article contains:
        - country: country the news is about
        - summary: summary of the news article
        - likelihood: risk rating (0-5)
        - likelihood_reasoning: explanation for the risk rating
        - description: type of political change (elections, strikes, etc.)
        - publication_date: date of the news article
        - source: publisher of the news article
        - source_url: URL link to the original article
        
        Returns a JSON array where each object represents a country with:
        - DateTime_stamp: when the data was generated
        - Country: name of the country
        - Average_Risk: average risk score (likelihood) for the country, rounded to nearest integer
        - Breakdown: array of all risk articles for that country
        """
        try:
            # Parse the input JSON array
            news_articles = json.loads(news_articles_json)
            
            # Get current timestamp
            timestamp = datetime.datetime.now().isoformat()
            
            # Group articles by country
            country_data = {}
            
            for article in news_articles:
                country = article.get("country")
                
                if not country:
                    continue  # Skip articles without a country
                    
                # Initialize country entry if not exists
                if country not in country_data:
                    country_data[country] = {
                        "risks": [],
                        "total_likelihood": 0,
                        "risk_count": 0
                    }
                
                # Add article to country's risks
                country_data[country]["risks"].append(article)
                
                # Update likelihood totals
                likelihood = article.get("likelihood", 0)
                country_data[country]["total_likelihood"] += likelihood
                country_data[country]["risk_count"] += 1
            
            # Create the final heatmap data
            heatmap_data = []
            
            for country, data in country_data.items():
                # Calculate average risk (rounded to nearest integer)
                avg_risk = round(data["total_likelihood"] / data["risk_count"]) if data["risk_count"] > 0 else 0
                
                # Sort the breakdown by likelihood (highest first) and then by date (newest first)
                sorted_risks = sorted(
                    data["risks"], 
                    key=lambda x: (-x.get("likelihood", 0), x.get("publication_date", ""))
                )
                
                # Create country entry
                country_entry = {
                    "DateTime_stamp": timestamp,
                    "Country": country,
                    "Average_Risk": avg_risk,
                    "Breakdown": sorted_risks
                }
                
                heatmap_data.append(country_entry)
            
            # Return the formatted JSON result
            return json.dumps(heatmap_data, indent=2)
        
        except Exception as e:
            return json.dumps({"error": f"Failed to generate country risk heatmap: {str(e)}"})