"""Integrações com bibliotecas: decorador, Sentry, structlog, loguru, LangChain, MCP e pandas."""

import asyncio
import io

import pytest

PII = "Sou a Maria Souza, CPF 529.982.247-25"


# Decorador -------------------------------------------------------------------------------------------------------

def test_protect_sync_function_and_arguments():
    from veu import protect

    seen = []

    @protect
    def answer(question: str, history: list, temperature: float = 0.2) -> str:
        seen.append((question, history, temperature))
        return "Olá [PESSOA_1], CPF [CPF_1]."

    assert answer(PII, [{"role": "user", "content": "Maria Souza aqui"}]) == "Olá Maria Souza, CPF 529.982.247-25."
    assert seen[-1] == ("Sou a [PESSOA_1], CPF [CPF_1]", [{"role": "user", "content": "[PESSOA_1] aqui"}], 0.2)


def test_protect_only_selected_arguments_and_no_restore():
    from veu import protect

    @protect(arguments=["question"], restore=False)
    def answer(question: str, system: str) -> str:
        return f"{question} | {system} | [CPF_1]"

    assert answer(PII, "Atenda Maria Souza") == "Sou a [PESSOA_1], CPF [CPF_1] | Atenda Maria Souza | [CPF_1]"


def test_protect_generators_and_async():
    from veu import protect

    @protect
    def stream(question):
        yield from ["Oi [PES", "SOA_1], CPF [CP", "F_1]"]

    @protect
    async def answer(question):
        return {"text": "Ok [PESSOA_1]"}

    @protect
    async def astream(question):
        for piece in ["Ok [PES", "SOA_1]"]:
            yield piece

    async def collect():
        return "".join([piece async for piece in astream(PII)])

    assert "".join(stream(PII)) == "Oi Maria Souza, CPF 529.982.247-25"
    assert asyncio.run(answer(PII)) == {"text": "Ok Maria Souza"}
    assert asyncio.run(collect()) == "Ok Maria Souza"


# Observabilidade --------------------------------------------------------------------------------------------------

def test_sentry_scrubs_event_but_keeps_technical_fields():
    from veu.integrations.sentry import before_breadcrumb, before_send

    event = {
        "event_id": "abc",
        "message": "Falha para o CPF 529.982.247-25",
        "exception": {"values": [{"type": "ValueError", "value": "Cliente Maria Souza sem saldo",
                                  "stacktrace": {"frames": [{"filename": "app.py", "vars": {"cpf": "'529.982.247-25'"}}]}}]},
        "request": {"data": {"telefone": "(11) 91234-5678"}},
        "user": {"email": "maria@example.com"},
        "contexts": {"os": {"name": "Windows"}, "user": {"nome": "Maria Souza"}},
    }
    scrubbed = before_send(event, {})
    text = str(scrubbed)
    assert "529.982.247-25" not in text and "Maria Souza" not in text and "maria@example.com" not in text
    assert scrubbed["event_id"] == "abc" and scrubbed["contexts"]["os"] == {"name": "Windows"}
    assert scrubbed["message"] == "Falha para o CPF [CPF]"
    assert before_breadcrumb({"message": "login de maria@example.com"}, {})["message"] == "login de [EMAIL]"


def test_structlog_processor():
    structlog = pytest.importorskip("structlog")
    from veu.integrations.structlog import PIIProcessor

    output = io.StringIO()
    structlog.configure(processors=[PIIProcessor(), structlog.processors.KeyValueRenderer(key_order=["event"])],
                        logger_factory=structlog.PrintLoggerFactory(output), cache_logger_on_first_use=False)
    structlog.get_logger().info("cadastro de Maria Souza", cpf="529.982.247-25", tentativas=2)
    structlog.reset_defaults()
    assert output.getvalue().strip() == "event='cadastro de [PESSOA]' cpf='[CPF]' tentativas=2"


def test_loguru_patcher():
    loguru = pytest.importorskip("loguru")
    from veu.integrations.loguru import pii_patcher

    messages = []
    logger = loguru.logger
    handler = logger.add(lambda message: messages.append((message.record["message"], dict(message.record["extra"]))),
                         format="{message}")
    try:
        logger.patch(pii_patcher()).bind(cliente="Maria Souza").info("CPF {} entrou", "529.982.247-25")
    finally:
        logger.remove(handler)
    assert messages == [("CPF [CPF] entrou", {"cliente": "[PESSOA]"})]


# LangChain --------------------------------------------------------------------------------------------------------

def test_langchain_invoke_chain_and_tool_calls():
    pytest.importorskip("langchain_core")
    from langchain_core.messages import AIMessage, HumanMessage
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.runnables import RunnableLambda

    from veu.integrations.langchain import protect_model

    seen = []

    def model(messages):
        seen.append(messages)
        return AIMessage(content="Olá [PESSOA_1], CPF [CPF_1].",
                         tool_calls=[{"name": "buscar", "args": {"cpf": "[CPF_1]"}, "id": "1"}])

    reply = protect_model(RunnableLambda(model)).invoke([HumanMessage(PII)])
    assert reply.content == "Olá Maria Souza, CPF 529.982.247-25."
    assert reply.tool_calls[0]["args"] == {"cpf": "529.982.247-25"}
    assert seen[-1][0].content == "Sou a [PESSOA_1], CPF [CPF_1]"
    prompt = ChatPromptTemplate.from_messages([("system", "Seja breve"), ("human", "{pergunta}")])
    chain = prompt | protect_model(RunnableLambda(model)) | StrOutputParser()
    assert chain.invoke({"pergunta": PII}) == "Olá Maria Souza, CPF 529.982.247-25."


def test_langchain_streaming_sync_and_async():
    pytest.importorskip("langchain_core")
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage

    from veu.integrations.langchain import protect_model

    model = GenericFakeChatModel(messages=iter([AIMessage(content="Olá [PESSOA_1], seu CPF [CPF_1] está ok.")]))
    chunks = list(protect_model(model).stream(PII))
    assert len(chunks) > 3
    assert "".join(chunk.content for chunk in chunks) == "Olá Maria Souza, seu CPF 529.982.247-25 está ok."

    async_model = GenericFakeChatModel(messages=iter([AIMessage(content="Oi [PESSOA_1]!")]))

    async def collect():
        return "".join([chunk.content async for chunk in protect_model(async_model).astream(PII)])

    assert asyncio.run(collect()) == "Oi Maria Souza!"


def test_langchain_document_transformer_shares_vault():
    pytest.importorskip("langchain_core")
    from langchain_core.documents import Document

    from veu.integrations.langchain import VeuDocumentTransformer

    documents, vault = VeuDocumentTransformer().anonymize([
        Document("Contrato de Maria Souza, CPF 529.982.247-25", metadata={"autor": "Carlos Lima"}),
        Document("Maria Souza pagou."),
    ])
    assert documents[0].page_content == "Contrato de [PESSOA_1], CPF [CPF_1]"
    assert documents[0].metadata == {"autor": "[PESSOA_2]"}
    assert documents[1].page_content == "[PESSOA_1] pagou."
    assert vault.restore("[PESSOA_1]") == "Maria Souza"


# MCP --------------------------------------------------------------------------------------------------------------

def test_mcp_tools(tmp_path):
    pytest.importorskip("mcp")
    from mcp.client import Client

    from veu.integrations.mcp import build_server

    source = tmp_path / "clientes.csv"
    source.write_text("nome,cpf\nJoana Prado,52998224725\n", encoding="utf-8")

    async def run():
        async with Client(build_server(restore_text=True)) as client:
            names = {tool.name for tool in (await client.list_tools()).tools}
            check = await client.call_tool("verificar_arquivo", {"caminho": str(source)})
            copy = await client.call_tool("anonimizar_arquivo", {
                "origem": str(source), "destino": str(tmp_path / "anon.csv"), "forcar": {"cpf": "CPF"},
                "salvar_cofre": str(tmp_path / "cofre.json"),
            })
            text = await client.call_tool("anonimizar_texto", {"texto": PII})
            restored = await client.call_tool("restaurar_texto", {"texto": "Olá [PESSOA_1]",
                                                                   "sessao": text.structured_content["sessao"]})
            back = await client.call_tool("restaurar_arquivo", {"origem": str(tmp_path / "anon.csv"),
                                                                "destino": str(tmp_path / "volta.csv"),
                                                                "cofre": str(tmp_path / "cofre.json")})
            missing = await client.call_tool("restaurar_texto", {"texto": "x", "sessao": "nao-existe"})
            return names, check, copy, text, restored, back, missing

    names, check, copy, text, restored, back, missing = asyncio.run(run())
    assert {"verificar_arquivo", "anonimizar_arquivo", "detectar", "anonimizar_texto", "restaurar_texto",
            "restaurar_arquivo", "listar_entidades"} <= names
    assert check.structured_content["por_entidade"] == {"PESSOA": 1, "CPF": 1}
    assert "52998224725" not in str(check.structured_content) and "Joana" not in str(check.structured_content)
    assert copy.structured_content["escondidos"] == {"PESSOA": 1, "CPF": 1}
    assert (tmp_path / "anon.csv").read_text(encoding="utf-8") == "nome,cpf\n[PESSOA_1],[CPF_1]\n"
    assert text.structured_content["texto"] == "Sou a [PESSOA_1], CPF [CPF_1]"
    assert restored.content[0].text == "Olá Maria Souza"
    assert (tmp_path / "volta.csv").read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
    assert not back.is_error
    assert missing.is_error and "Sessão não encontrada" in missing.content[0].text


# pandas -----------------------------------------------------------------------------------------------------------

def test_pandas_round_trip_with_forced_columns():
    pd = pytest.importorskip("pandas")
    from veu.integrations.pandas import anonymize_dataframe, restore_dataframe

    df = pd.DataFrame({
        "nome": ["Joana Prado", "Carlos Lima", "Joana Prado"],
        "cpf": ["52998224725", "99999999999", "52998224725"],
        "obs": ["ligar (11) 91234-5678", None, "sem contato"],
        "valor": [10.5, 20.0, 30.0],
    })
    anonymous, vault = anonymize_dataframe(df, force={"cpf": "CPF"})
    assert list(anonymous["nome"]) == ["[PESSOA_1]", "[PESSOA_2]", "[PESSOA_1]"]
    assert list(anonymous["cpf"]) == ["[CPF_1]", "[CPF_2]", "[CPF_1]"]
    assert anonymous["obs"].iloc[0] == "ligar [TELEFONE_1]" and pd.isna(anonymous["obs"].iloc[1])
    assert list(anonymous["valor"]) == [10.5, 20.0, 30.0]
    assert restore_dataframe(anonymous, vault).equals(df)
    with pytest.raises(KeyError):
        anonymize_dataframe(df, columns=["inexistente"])
