import httpx
import asyncio

async def test():
    key = 'sk_vdlpdnbl_kwuZxLOIcJbkTCsfHae4MRtw'
    async with httpx.AsyncClient() as client:
        r = await client.post(
            'https://api.sarvam.ai/text-to-speech',
            headers={'api-subscription-key': key, 'Content-Type': 'application/json'},
            json={'text': 'kaise bani', 'target_language_code': 'bho-IN', 'model': 'bulbul:v3', 'speaker': 'shubh'}
        )
        print(f"TTS Status: {r.status_code}")
        print(f"TTS Body: {r.text[:200]}")

        r2 = await client.post(
            'https://api.sarvam.ai/v1/chat/completions',
            headers={'api-subscription-key': key, 'Content-Type': 'application/json'},
            json={"model": "sarvam-30b", "messages": [{"role": "user", "content": "hello"}]}
        )
        print(f"LLM Status: {r2.status_code}")
        print(f"LLM Body: {r2.text[:200]}")

if __name__ == "__main__":
    asyncio.run(test())
