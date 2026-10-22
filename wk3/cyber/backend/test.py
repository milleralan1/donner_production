import os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["GROQ_API_KEY"],
    base_url="https://api.groq.com/openai/v1",
)

models = sorted(client.models.list().data, key=lambda m: m.id)

print(f"{len(models)} models available:\n")
for m in models:
    print(f"{m.id:<55} owned_by={m.owned_by}")