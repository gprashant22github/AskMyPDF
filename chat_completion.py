import os

from sarvamai import SarvamAI


api_key = os.environ.get("SARVAM_API_KEY")
if not api_key:
    raise RuntimeError("SARVAM_API_KEY is not set")

client = SarvamAI(api_subscription_key=api_key)
response = client.chat.completions(
    model="sarvam-105b-conversations",
    messages=[{"role": "user", "content": "Say hello in one short sentence."}],
)

print(response.choices[0].message.content)
