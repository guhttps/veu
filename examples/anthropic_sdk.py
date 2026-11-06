"""Claude (Anthropic) protegido pelo Véu, sem proxy.

    pip install "veu[httpx]" anthropic
    ANTHROPIC_API_KEY=... python examples/anthropic_sdk.py
"""

from veu.integrations.sdk import anthropic_client

client = anthropic_client()  # mesmos argumentos de anthropic.Anthropic(...)

with client.messages.stream(
    model="claude-sonnet-4-5",
    max_tokens=300,
    messages=[{
        "role": "user",
        "content": "Paciente João Pedro Oliveira, cartão SUS 898 0010 0123 4567, nascido em 12/03/1980. "
                   "Resuma o caso em uma frase para a recepção.",
    }],
) as stream:
    for texto in stream.text_stream:
        print(texto, end="", flush=True)
print()
