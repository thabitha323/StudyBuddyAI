from google import genai

client = genai.Client(api_key="OPENROUTER_API_KE")

response = client.models.generate_content(
    model="gemini-flash-latest",
    contents="Say hello"
)
print(response.text)