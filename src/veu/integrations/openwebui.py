"""Filtro do Véu para o Open WebUI (beta).

No Open WebUI, em Painel do administrador > Funções > Criar, cole o conteúdo de examples/open-webui/veu.py (ele só
importa esta classe e pede o pacote veu). Depois ative a função e escolha os modelos em que ela vale.

- inlet: esconde dados pessoais e segredos das mensagens antes de irem ao modelo (o mesmo marcador para o mesmo
  dado em toda a conversa);
- stream: devolve os dados reais nos pedaços da resposta, quando o Open WebUI informa de qual conversa eles são;
- outlet: devolve os dados reais na mensagem final, que é a que fica salva.

O cofre de cada conversa fica só na memória do Open WebUI e expira depois de uma hora sem uso. Um pedaço de resposta
sem a identificação da conversa nunca é restaurado com o cofre de outra: num Open WebUI com várias pessoas, isso
mostraria os dados de alguém para outra pessoa.
"""

from __future__ import annotations

from typing import Any

from veu.anonymizer import normalize_operator
from veu.core import Veu
from veu.server.state import SessionStore
from veu.vault import StreamRestorer

try:  # o Open WebUI usa pydantic para mostrar as opções (valves) na tela
    from pydantic import BaseModel
except ImportError:  # pragma: no cover - fora do Open WebUI, uma classe simples basta
    BaseModel = object  # type: ignore[assignment,misc]


def _chat_id(metadata: dict | None, body: dict | None = None) -> str | None:
    for source in (metadata or {}, (body or {}).get("metadata") or {}):
        if source.get("chat_id"):
            return str(source["chat_id"])
    return None


class Filter:
    class Valves(BaseModel):
        priority: int = 0
        operador: str = "token"
        bloquear: str = "CHAVE_PRIVADA"
        restaurar_respostas: bool = True

    def __init__(self):
        self.valves = self.Valves()
        self._veu: Veu | None = None
        self._key: tuple | None = None
        self._sessions: SessionStore | None = None
        self._restorers: dict[str, StreamRestorer] = {}

    def _engine(self) -> Veu:
        key = (self.valves.operador, self.valves.bloquear)
        if self._veu is None or key != self._key:
            self._veu = Veu(operator=normalize_operator(self.valves.operador))
            self._sessions = SessionStore(self._veu.new_vault, ttl=3600)
            self._key = key
        return self._veu

    def _vault(self, chat_id: str, create: bool = True):
        self._engine()
        return self._sessions.get(chat_id, create=create)

    def inlet(self, body: dict, __user__: dict | None = None, __metadata__: dict | None = None) -> dict:
        veu = self._engine()
        chat_id = _chat_id(__metadata__, body) or SessionStore.new_id()  # sem conversa: um cofre só para este pedido
        vault = self._vault(chat_id)
        blocked = {label.strip().upper() for label in self.valves.bloquear.split(",") if label.strip()}
        found: set[str] = set()
        for message in body.get("messages") or []:
            content = message.get("content")
            if isinstance(content, str):
                result = veu.anonymize(content, vault)
                message["content"] = result.text
                found |= set(result.counts())
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str):
                        result = veu.anonymize(part["text"], vault)
                        part["text"] = result.text
                        found |= set(result.counts())
        if found & blocked:
            raise ValueError(f"O Véu recusou a mensagem: ela contém {', '.join(sorted(found & blocked))}.")
        return body

    def stream(self, event: dict, __metadata__: dict | None = None, **_: Any) -> dict:
        chat_id = _chat_id(__metadata__)
        if not self.valves.restaurar_respostas or chat_id is None:
            return event  # sem saber a conversa, nunca restaura (o outlet restaura a mensagem final)
        vault = self._vault(chat_id, create=False)
        if vault is None:
            return event
        restorer = self._restorers.setdefault(chat_id, vault.restorer())
        for choice in event.get("choices") or []:
            delta = choice.get("delta") or {}
            if isinstance(delta.get("content"), str):
                delta["content"] = restorer.feed(delta["content"])
            if choice.get("finish_reason"):
                delta["content"] = (delta.get("content") or "") + restorer.flush()
                self._restorers.pop(chat_id, None)
        return event

    def outlet(self, body: dict, __user__: dict | None = None, __metadata__: dict | None = None) -> dict:
        chat_id = _chat_id(__metadata__, body) or str(body.get("chat_id") or "")
        self._restorers.pop(chat_id, None)
        vault = self._vault(chat_id, create=False) if chat_id and self.valves.restaurar_respostas else None
        if vault is None:
            return body
        for message in body.get("messages") or []:
            if message.get("role") == "assistant" and isinstance(message.get("content"), str):
                message["content"] = vault.restore(message["content"])
        return body
