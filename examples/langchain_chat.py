"""LangChain com o Véu: o modelo recebe [PESSOA_1] e [CPF_1]; a cadeia devolve os dados reais.

    pip install "veu[langchain] @ git+https://github.com/guhttps/veu" langchain-openai
    OPENAI_API_KEY=... python examples/langchain_chat.py
"""

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from veu.integrations.langchain import protect_model

prompt = ChatPromptTemplate.from_messages([
    ("system", "Você é um atendente educado. Responda em uma frase."),
    ("human", "{pergunta}"),
])
cadeia = prompt | protect_model(ChatOpenAI(model="gpt-4o-mini")) | StrOutputParser()

pergunta = "Sou a Maria Souza, CPF 529.982.247-25, e meu pedido não chegou."
print(cadeia.invoke({"pergunta": pergunta}))

# Streaming: os marcadores partidos entre pedaços são remontados antes de chegar aqui.
for pedaco in cadeia.stream({"pergunta": pergunta}):
    print(pedaco, end="", flush=True)
print()
