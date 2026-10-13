import serpapi

url= "https://serpapi.com/search.json?engine=google&q=Coffee"
client = serpapi.Client(api_key="secret_api_key")
results = client.search({
  "engine": "google",
  "q": "Coffee"
})
organic_results = results["organic_results"]