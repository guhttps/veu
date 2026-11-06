"""Chat com a OpenAI protegido pelo Véu, sem proxy.

    pip install "veu[httpx]" openai
    OPENAI_API_KEY=... python examples/openai_sdk.py
"""

from veu.integrations.sdk import openai_client

client = openai_client()  # mesmos argumentos de openai.OpenAI(...)

pergunta = (
    "Sou a Maria Aparecida da Silva, CPF 529.982.247-25, e moro na Rua das Flores, 123. "
    "Escreva uma mensagem curta confirmando meu cadastro."
)
resposta = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": pergunta}])

# O modelo recebeu [PESSOA_1], [CPF_1] e [ENDERECO_1]; a resposta chega com os dados reais.
print(resposta.choices[0].message.content)

print("\nEm streaming:")
for pedaco in client.chat.completions.create(
    model="gpt-4o-mini", messages=[{"role": "user", "content": pergunta}], stream=True
):
    if pedaco.choices:
        print(pedaco.choices[0].delta.content or "", end="", flush=True)
print()
