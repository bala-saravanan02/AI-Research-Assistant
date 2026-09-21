import asyncio
import httpx
from bs4 import BeautifulSoup
from mcp.server import MCPServer  # Use the standardized MCPServer wrapper class
from mcp.server.stdio import stdio_server


# 1. Initialize the Server & Tool Registry Container
mcp = MCPServer("Keyless-Research-Assistant")

# 2. Register the Search Tool into the Catalog
@mcp.tool()
async def keyless_web_search(query: str) -> str:
    """
    Performs a live web search using DuckDuckGo HTML parsing.
    No API keys or pricing tiers required.
    """
    url = "https://html.duckduckgo.com/html/"
    headers = {"User-Agent": "Mozilla/5.0 (Windows) AppleWebKit/537.36"}
    
    try:
        async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
            response = await client.get(url, params={"q": query})
            
        if response.status_code != 200:
            return f"Search engine issue encountered. HTTP Code: {response.status_code}"

        soup = BeautifulSoup(response.text, "html.parser")
        snippets = []
        
        for body in soup.find_all("div", class_="result__body")[:5]:
            title = body.find("a", class_="result__url")
            snippet = body.find("a", class_="result__snippet")
            if title and snippet:
                snippets.append(f"Title: {title.get_text(strip=True)}\nSnippet: {snippet.get_text(strip=True)}")
        
        return "\n\n".join(snippets) if snippets else "No context found for this keyword selection."
    except Exception as e:
        return f"Scraper execution failure: {str(e)}"

# 3. Expose the server process via native stdio transport standard streams
async def main():
    async with stdio_server() as (read_stream, write_stream):
        await mcp.run(read_stream, write_stream, mcp.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
