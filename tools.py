from langchain.tools import tool
import requests
from bs4 import BeautifulSoup
from tavily import TavilyClient
import os
from dotenv import load_dotenv
load_dotenv()
from rich import print

tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEYS"))

@tool
def web_search(query : str)-> str:
     """Search the web for recent reliable information on a topic. Returns Titles , URLs and snippets."""

     results = tavily.search(query=query,max_results=5)

     search_results = []

     for i, result in enumerate(results["results"], start=1):
          search_results.append(
          f"{i}. {result['title']}\n"
          f"URL: {result['url']}\n"
          f"Snippet: {result['content'][:300]}"
    )

     return "\n\n".join(search_results)    

@tool
def scrape_url(url: str) -> str:
    """Scrape and return clean text content from a given URL for deeper reading."""
    try:
        resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})

        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
            
        return soup.get_text(separator=" ", strip=True)[:3000]
    except Exception as e:
        return f"Could not scrape URL: {str(e)}"       
