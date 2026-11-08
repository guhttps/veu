"""Kit de conformidade: perfis prontos e o registro das operações (LGPD, art. 37) a partir da auditoria."""

import asyncio
import json

import httpx
import pytest

from veu import Veu
from veu.cli import main
from veu.config import PROFILES, Config, ConfigError, load_config
from veu.server import create_app
from veu.server.state import AuditLog, audit_report

TEXT = "Maria Souza, CPF 529.982.247-25, cartão 4111 1111 1111 1111"


def test_anonymization_profile_is_irreversible():
    veu = Veu(Config().with_profile("anonimizacao"))
    result = veu.anonymize(TEXT)
    assert result.text == "[PESSOA], CPF [CPF], cartão [CARTAO_CREDITO]"
    assert len(result.vault) == 0  # nenhum valor guardado: não há o que restaurar


def test_financial_profile_removes_cards_but_keeps_names_reversible():
    result = Veu(Config().with_profile("financeiro")).anonymize(TEXT)
    assert result.text == "[PESSOA_1], CPF [CPF_1], cartão [CARTAO_CREDITO]"
    assert result.restore("Olá [PESSOA_1]") == "Olá Maria Souza"


def test_public_sector_profile_refuses_any_personal_data():
    seen = []
    app = create_app(Config().with_profile("setor-publico"),
                     upstream_transport=httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(200, json={})))

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8787") as c:
            return await c.post("/v1/chat/completions", json={"model": "m", "messages": [
                {"role": "user", "content": TEXT}]})

    assert asyncio.run(run()).status_code == 400 and not seen


def test_profile_from_toml_and_explicit_options_win(tmp_path):
    path = tmp_path / "veu.toml"
    path.write_text('[politica]\nperfil = "judiciario"\nbloquear = ["CARTAO_CREDITO"]\n', encoding="utf-8")
    config = load_config(str(path), environ={})
    assert config.profile == "judiciario" and config.operator == "remover"
    assert config.block == ("CARTAO_CREDITO",)  # o que está escrito no arquivo vale mais que o perfil
    assert load_config(None, environ={"VEU_PERFIL": "saude"}).route_labels == ("CNS",)


def test_unknown_profile():
    with pytest.raises(ConfigError, match="Perfil desconhecido"):
        Config(profile="inventado")
    with pytest.raises(ConfigError, match="Perfil desconhecido"):
        Config().with_profile("inventado")


def test_every_profile_is_valid_and_described():
    for name, profile in PROFILES.items():
        assert profile["descricao"] and Config().with_profile(name).profile == name


def test_cli_profiles_and_flag(capsys, tmp_path):
    assert main(["perfis"]) == 0
    assert "anonimizacao" in capsys.readouterr().out
    source = tmp_path / "entrada.txt"
    source.write_text(TEXT, encoding="utf-8")
    assert main(["anonimizar", str(source), "--perfil", "anonimizacao"]) == 0
    assert "[CPF]" in capsys.readouterr().out


def test_audit_report_has_only_metadata(tmp_path):
    path = tmp_path / "auditoria.jsonl"
    log = AuditLog(str(path))
    log.write(provedor="openai", status=200, entidades={"CPF": 2, "PESSOA": 1}, restaurados={"PESSOA": 1},
              equipe="juridico")
    log.write(provedor="anthropic", status=400, bloqueado=["CHAVE_PRIVADA"], entidades={"CHAVE_PRIVADA": 1})
    log.write(provedor="openai", status=502, entidades={})
    text = audit_report(path)
    assert "LGPD, art. 37" in text and "íntegra" in text and "| CPF | 2 |" in text and "| CHAVE_PRIVADA | 1 |" in text
    data = json.loads(audit_report(path, fmt="json"))
    assert data["operacoes"] == {"requisicoes": 3, "bloqueadas": 1, "desviadas": 0, "sem_anonimizar": 0, "erros": 1}
    assert data["por_provedor"] == {"openai": 2, "anthropic": 1} and data["dados_restaurados"] == {"PESSOA": 1}
    assert json.loads(audit_report(path, fmt="json", since="2999-01-01"))["operacoes"] == {}


def test_audit_report_cli(tmp_path, capsys):
    path = tmp_path / "auditoria.jsonl"
    AuditLog(str(path)).write(provedor="openai", status=200, entidades={"CPF": 1})
    assert main(["auditoria", "relatorio", str(path), "--formato", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["dados_escondidos"] == {"CPF": 1}
