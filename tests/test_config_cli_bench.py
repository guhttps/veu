import json

import pytest

from veu.bench.evaluate import evaluate
from veu.bench.generator import generate, load, save
from veu.bench.hard import hard_samples
from veu.cli import main
from veu.config import ConfigError, load_config


def test_toml_and_environment(tmp_path):
    file = tmp_path / "veu.toml"
    file.write_text(
        """
[deteccao]
limiar = 0.7
ignorar = ["contato@empresa.com.br"]

[[deteccao.personalizados]]
entidade = "MATRICULA"
padrao = "MAT-\\\\d{6}"

[anonimizacao]
operador = "sintetico"

[anonimizacao.operadores]
CARTAO_CREDITO = "remover"

[politica]
bloquear = ["cartao_credito"]

[servidor]
porta = 9000

[provedores.interno]
tipo = "openai"
url = "http://ia.interna/v1/"
""",
        encoding="utf-8",
    )
    config = load_config(file, environ={"VEU_PORTA": "9100", "VEU_URL_GROQ": "http://proxy-groq/v1"})
    assert config.threshold == 0.7
    assert config.operator == "sintetico"
    assert config.operators == {"CARTAO_CREDITO": "remover"}
    assert config.block == ("CARTAO_CREDITO",)
    assert config.port == 9100
    assert config.providers["interno"].url == "http://ia.interna/v1"
    assert config.providers["groq"].url == "http://proxy-groq/v1"
    assert config.custom_patterns[0]["entidade"] == "MATRICULA"


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("[deteccao]\nlimiar = 2", "limiar"),
        ("[deteccao]\nentidades = ['XYZ']", "Entidades desconhecidas"),
        ("[anonimizacao]\noperador = 'apagar'", "Operador desconhecido"),
        ("[outra]\na = 1", "Seção desconhecida"),
        ("[servidor]\nporto = 1", "Opção desconhecida"),
    ],
)
def test_invalid_config_is_explained(tmp_path, content, message):
    file = tmp_path / "veu.toml"
    file.write_text(content, encoding="utf-8")
    with pytest.raises((ConfigError, ValueError), match=message):
        load_config(file, environ={})


def test_cli_round_trip(tmp_path, capsys):
    source = tmp_path / "entrada.txt"
    source.write_text("Cliente Joana Prado, CPF 529.982.247-25", encoding="utf-8")
    vault = tmp_path / "cofre.json"
    output = tmp_path / "saida.txt"
    assert main(["anonimizar", str(source), "--cofre", str(vault), "-o", str(output)]) == 0
    assert output.read_text(encoding="utf-8") == "Cliente [PESSOA_1], CPF [CPF_1]"
    reply = tmp_path / "resposta.txt"
    reply.write_text("Olá [PESSOA_1]", encoding="utf-8")
    capsys.readouterr()
    assert main(["restaurar", str(reply), "--cofre", str(vault)]) == 0
    assert capsys.readouterr().out == "Olá Joana Prado"


def test_cli_detect_json(tmp_path, capsys):
    source = tmp_path / "a.txt"
    source.write_text("email ana@x.com.br", encoding="utf-8")
    assert main(["detectar", str(source), "--json"]) == 0
    found = json.loads(capsys.readouterr().out)
    assert found[0]["entidade"] == "EMAIL"


def test_cli_check_for_pre_commit(tmp_path, capsys):
    clean = tmp_path / "limpo.py"
    clean.write_text("print('olá')\n", encoding="utf-8")
    dirty = tmp_path / "sujo.py"
    dirty.write_text("cpf = '529.982.247-25'\nteste = '111.444.777-35'  # veu: ignorar\n", encoding="utf-8")
    assert main(["verificar", str(clean)]) == 0
    assert main(["verificar", str(clean), str(dirty)]) == 1
    out = capsys.readouterr().out
    assert "sujo.py:1:8: CPF" in out and "***.982.247-**" in out
    assert "529.982.247-25" not in out and "111.444" not in out


def test_benchmark_generation_is_deterministic_and_annotated(tmp_path):
    first, second = generate(80, seed=3), generate(80, seed=3)
    assert [s.text for s in first] == [s.text for s in second]
    for sample in first:
        for start, end, label in sample.entities:
            assert sample.text[start:end].strip() == sample.text[start:end]
            assert label
    path = tmp_path / "dataset.jsonl"
    save(first, path)
    assert [s.to_dict() for s in load(path)] == [s.to_dict() for s in first]


def test_benchmark_quality_gates():
    development = evaluate(generate(400, seed=42))
    validation = evaluate(generate(400, seed=43, validation=True))
    hard = evaluate(hard_samples())
    assert development.overall.leak_rate < 0.01
    assert validation.overall.leak_rate < 0.05
    assert validation.overall.precision > 0.97
    assert hard.overall.leak_rate == 0


def test_example_config_is_valid():
    from pathlib import Path

    config = load_config(Path(__file__).parent.parent / "examples" / "veu.toml", environ={})
    assert config.providers["interno"].url == "https://ia.minhaempresa.com/v1"
    assert config.operators["CARTAO_CREDITO"] == "remover"
