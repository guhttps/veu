"""Integração nativa com o LangChain (pip install langchain-core).

    from langchain_openai import ChatOpenAI
    from veu.integrations.langchain import protect_model, VeuDocumentTransformer

    modelo = protect_model(ChatOpenAI(model="gpt-4o-mini"))
    cadeia = prompt | modelo | StrOutputParser()      # funciona em qualquer posição da cadeia

    documentos, cofre = VeuDocumentTransformer().anonymize(documentos)   # RAG: indexe já anonimizado

O wrapper anonimiza a entrada (texto, mensagens ou prompt), chama o modelo e restaura a saída,
inclusive em streaming e nos argumentos das chamadas de ferramentas.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any

from langchain_core.documents import BaseDocumentTransformer, Document
from langchain_core.messages import AIMessageChunk, BaseMessage
from langchain_core.prompt_values import PromptValue
from langchain_core.runnables import Runnable, RunnableConfig

from veu.core import Veu
from veu.vault import Vault


def _mask_message(message: BaseMessage, session) -> BaseMessage:
    update: dict[str, Any] = {}
    if isinstance(message.content, str):
        update["content"] = session.anonymize(message.content)
    elif isinstance(message.content, list):
        parts = []
        for part in message.content:
            if isinstance(part, str):
                parts.append(session.anonymize(part))
            elif isinstance(part, dict) and part.get("type") == "text":
                parts.append({**part, "text": session.anonymize(part.get("text", ""))})
            else:
                parts.append(part)
        update["content"] = parts
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        update["tool_calls"] = [{**call, "args": session.anonymize_data(call.get("args", {}))} for call in tool_calls]
    return message.model_copy(update=update)


def _restore_message(message: BaseMessage, session) -> BaseMessage:
    update: dict[str, Any] = {}
    if isinstance(message.content, str):
        update["content"] = session.restore(message.content)
    elif isinstance(message.content, list):
        update["content"] = session.restore_data(message.content)
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        update["tool_calls"] = [{**call, "args": session.restore_data(call.get("args", {}))} for call in tool_calls]
    return message.model_copy(update=update)


class VeuRunnable(Runnable):
    """Envolve um modelo ou cadeia do LangChain: entrada anonimizada, saída restaurada."""

    def __init__(self, bound: Runnable, veu: Veu | None = None):
        self.bound = bound
        self.veu = veu or Veu()

    @property
    def InputType(self):  # noqa: N802 (nome definido pelo LangChain)
        return self.bound.InputType

    @property
    def OutputType(self):  # noqa: N802
        return self.bound.OutputType

    # Entrada e saída
    def _mask(self, value: Any, session) -> Any:
        if isinstance(value, str):
            return session.anonymize(value)
        if isinstance(value, BaseMessage):
            return _mask_message(value, session)
        if isinstance(value, PromptValue):
            return [_mask_message(message, session) for message in value.to_messages()]
        if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
            return [self._mask(item, session) for item in value]
        if isinstance(value, dict):
            return {key: self._mask(item, session) for key, item in value.items()}
        return value

    def _restore(self, value: Any, session) -> Any:
        if isinstance(value, str):
            return session.restore(value)
        if isinstance(value, BaseMessage):
            return _restore_message(value, session)
        if isinstance(value, (list, tuple)):
            return type(value)(self._restore(item, session) for item in value)
        if isinstance(value, dict):
            return {key: self._restore(item, session) for key, item in value.items()}
        return value

    def invoke(self, input: Any, config: RunnableConfig | None = None, **kwargs: Any) -> Any:
        session = self.veu.session()
        return self._restore(self.bound.invoke(self._mask(input, session), config, **kwargs), session)

    async def ainvoke(self, input: Any, config: RunnableConfig | None = None, **kwargs: Any) -> Any:
        session = self.veu.session()
        return self._restore(await self.bound.ainvoke(self._mask(input, session), config, **kwargs), session)

    # Streaming
    class _ChunkRestorer:
        def __init__(self, session):
            self.session = session
            self.text = session.restorer()
            self.arguments: dict[Any, Any] = {}
            self.last_chunk: Any = None

        def chunk(self, chunk: Any) -> Any:
            if isinstance(chunk, str):
                return self.text.feed(chunk) or None
            if isinstance(chunk, AIMessageChunk):
                self.last_chunk = chunk
                update: dict[str, Any] = {}
                if isinstance(chunk.content, str):
                    update["content"] = self.text.feed(chunk.content)
                if chunk.tool_call_chunks:
                    calls = []
                    for call in chunk.tool_call_chunks:
                        key = call.get("index", call.get("id"))
                        restorer = self.arguments.setdefault(key, self.session.vault.restorer(json_escape=True))
                        calls.append({**call, "args": restorer.feed(call.get("args") or "")})
                    update["tool_call_chunks"] = calls
                return chunk.model_copy(update=update)
            if isinstance(chunk, (dict, list)):
                return self.session.restore_data(chunk)
            return chunk

        def tail(self) -> Any:
            text = self.text.flush()
            calls = [{"index": key, "args": tail, "name": None, "id": None, "type": "tool_call_chunk"}
                     for key, restorer in self.arguments.items() if (tail := restorer.flush())]
            if isinstance(self.last_chunk, AIMessageChunk):
                if text or calls:
                    return AIMessageChunk(content=text, tool_call_chunks=calls)
                return None
            return text or None

    def stream(self, input: Any, config: RunnableConfig | None = None, **kwargs: Any) -> Iterator[Any]:
        session = self.veu.session()
        restorer = self._ChunkRestorer(session)
        for chunk in self.bound.stream(self._mask(input, session), config, **kwargs):
            output = restorer.chunk(chunk)
            if output is not None:
                yield output
        tail = restorer.tail()
        if tail is not None:
            yield tail

    async def astream(self, input: Any, config: RunnableConfig | None = None, **kwargs: Any) -> AsyncIterator[Any]:
        session = self.veu.session()
        restorer = self._ChunkRestorer(session)
        async for chunk in self.bound.astream(self._mask(input, session), config, **kwargs):
            output = restorer.chunk(chunk)
            if output is not None:
                yield output
        tail = restorer.tail()
        if tail is not None:
            yield tail


def protect_model(model: Runnable, veu: Veu | None = None) -> VeuRunnable:
    """Devolve o modelo (ou cadeia) protegido pelo Véu."""
    return VeuRunnable(model, veu)


class VeuDocumentTransformer(BaseDocumentTransformer):
    """Anonimiza o texto (e os metadados de texto) de documentos antes de indexar num banco vetorial.

    Todos os documentos usam o mesmo cofre, então o mesmo CPF vira o mesmo marcador em todo o índice.
    Guarde o cofre (vault.to_dict()) para restaurar as respostas geradas a partir do índice.
    """

    def __init__(self, veu: Veu | None = None, vault: Vault | None = None, metadata: bool = True):
        self._session = (veu or Veu()).session(vault)
        self.metadata = metadata

    @property
    def vault(self) -> Vault:
        return self._session.vault

    def transform_documents(self, documents: Sequence[Document], **kwargs: Any) -> Sequence[Document]:
        return [
            Document(
                page_content=self._session.anonymize(document.page_content),
                metadata=self._session.anonymize_data(document.metadata) if self.metadata else document.metadata,
                id=document.id,
            )
            for document in documents
        ]

    def anonymize(self, documents: Sequence[Document]) -> tuple[list[Document], Vault]:
        return list(self.transform_documents(documents)), self.vault
