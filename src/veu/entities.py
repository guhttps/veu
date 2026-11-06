"""Tipos de dados pessoais detectados pelo Véu."""

from __future__ import annotations

from dataclasses import dataclass

LABELS: dict[str, str] = {
    "PESSOA": "Nome de pessoa",
    "CPF": "CPF",
    "CNPJ": "CNPJ (numérico ou alfanumérico)",
    "RG": "RG",
    "CNH": "CNH",
    "TITULO_ELEITOR": "Título de eleitor",
    "PIS": "PIS, PASEP, NIT ou NIS",
    "CNS": "Cartão Nacional de Saúde (SUS)",
    "PASSAPORTE": "Passaporte",
    "TELEFONE": "Telefone",
    "EMAIL": "E-mail",
    "ENDERECO": "Endereço",
    "CEP": "CEP",
    "PLACA": "Placa de veículo",
    "RENAVAM": "RENAVAM",
    "CARTAO_CREDITO": "Cartão de crédito ou débito",
    "CONTA_BANCARIA": "Agência ou conta bancária",
    "CHAVE_PIX": "Chave Pix aleatória",
    "DATA_NASCIMENTO": "Data de nascimento",
    "IP": "Endereço IP",
    "PROCESSO": "Número de processo judicial (CNJ)",
    "IBAN": "IBAN (conta bancária internacional)",
    "CHAVE_API": "Chave de API ou token de serviço (OpenAI, AWS, GitHub...)",
    "TOKEN": "Token de acesso (JWT, Bearer)",
    "SENHA": "Senha",
    "CHAVE_PRIVADA": "Chave privada (PEM, SSH)",
    "URL_CONEXAO": "URL de conexão com usuário e senha",
    "SEGREDO": "Segredo em configuração (API_KEY=..., client_secret: ...)",
}

# Tipos que são segredos técnicos, não dados pessoais.
SECRET_LABELS = frozenset({"CHAVE_API", "TOKEN", "SENHA", "CHAVE_PRIVADA", "URL_CONEXAO", "SEGREDO"})


@dataclass(frozen=True, slots=True)
class Entity:
    """Um dado pessoal encontrado no texto."""

    label: str
    start: int
    end: int
    score: float
    text: str
    recognizer: str = ""

    def overlaps(self, other: Entity) -> bool:
        return self.start < other.end and other.start < self.end

    def to_dict(self) -> dict:
        return {
            "entidade": self.label,
            "inicio": self.start,
            "fim": self.end,
            "pontuacao": round(self.score, 2),
            "texto": self.text,
            "detector": self.recognizer,
        }
