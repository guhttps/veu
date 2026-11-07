import json
import random

import pytest

import veu
from veu import Vault, Veu
from veu.anonymizer import mask_value, normalize_operator

TEXT = (
    "O cliente João da Silva (CPF 529.982.247-25, tel (11) 91234-5678) pediu reembolso. "
    "João disse que o e-mail é joao.silva@example.com."
)


def test_tokens_are_consistent_and_restorable():
    result = veu.anonymize(TEXT)
    assert result.text == (
        "O cliente [PESSOA_1] (CPF [CPF_1], tel [TELEFONE_1]) pediu reembolso. "
        "[PESSOA_1] disse que o e-mail é [EMAIL_1]."
    )
    reply = "Olá [PESSOA_1], o CPF [CPF_1] e o telefone [TELEFONE_1] foram confirmados."
    assert result.restore(reply) == (
        "Olá João da Silva, o CPF 529.982.247-25 e o telefone (11) 91234-5678 foram confirmados."
    )


def test_same_value_in_different_formats_gets_same_token():
    result = veu.anonymize("CPF 529.982.247-25 ou 52998224725")
    assert result.text == "CPF [CPF_1] ou [CPF_1]"


def test_partial_name_before_full_name_is_linked():
    result = veu.anonymize("Oi, eu sou a Ana. Meu nome completo é Ana Beatriz Moura.")
    tokens = [item.replacement for item in result.replacements if item.label == "PESSOA"]
    assert len(set(tokens)) == 1


def test_shared_vault_keeps_tokens_across_texts():
    vault = Vault()
    first = veu.anonymize("CPF 529.982.247-25", vault)
    second = veu.anonymize("Também o 111.444.777-35 e o 529.982.247-25", vault)
    assert first.text == "CPF [CPF_1]"
    assert second.text == "Também o [CPF_2] e o [CPF_1]"


@pytest.mark.parametrize(
    "reply",
    ["[CPF 1]", "[cpf_1]", "CPF_1", "[ CPF_1 ]", "[CPF_1"],
)
def test_restore_tolerates_how_models_rewrite_tokens(reply):
    result = veu.anonymize("CPF 529.982.247-25")
    assert result.restore(reply) == "529.982.247-25"


def test_unknown_tokens_are_left_alone():
    result = veu.anonymize("CPF 529.982.247-25")
    assert result.restore("[CPF_9] e [PESSOA_1]") == "[CPF_9] e [PESSOA_1]"


def test_synthetic_operator_produces_valid_lookalikes_and_restores():
    from veu.validators import is_valid_cpf, is_valid_phone

    result = Veu(operator="sintetico").anonymize(TEXT)
    by_label = {item.label: item.replacement for item in result.replacements}
    assert is_valid_cpf(by_label["CPF"]) and by_label["CPF"] != "529.982.247-25"
    assert is_valid_phone(by_label["TELEFONE"])
    assert by_label["EMAIL"].rsplit("@", 1)[1] in ("example.com", "example.org", "example.net", "empresa.example")
    assert "João" not in result.text and "529.982.247-25" not in result.text
    # O modelo pode tirar a pontuação do CPF falso; a restauração continua funcionando.
    digits = by_label["CPF"].replace(".", "").replace("-", "")
    assert result.restore(f"CPF {digits}") == "CPF 529.982.247-25"
    assert result.restore(f"Olá, {by_label['PESSOA'].upper()}") == "Olá, João da Silva"


def test_irreversible_operators():
    assert Veu(operator="remover").anonymize("CPF 529.982.247-25").text == "CPF [CPF]"
    assert Veu(operator="mascara").anonymize("CPF 529.982.247-25").text == "CPF ***.982.247-**"
    assert mask_value("EMAIL", "joao@example.com") == "j***@example.com"
    assert mask_value("PESSOA", "João da Silva") == "J*** da S***"


def test_hash_operator_is_stable_with_same_secret():
    first = Veu(operator="hash", secret="segredo-de-teste-com-32-caracteres!!").anonymize("CPF 529.982.247-25").text
    second = Veu(operator="hash", secret="segredo-de-teste-com-32-caracteres!!").anonymize("CPF 529.982.247-25").text
    other = Veu(operator="hash", secret="outro-segredo-de-teste-com-32-caracteres").anonymize("CPF 529.982.247-25").text
    assert first == second != other
    assert first.startswith("CPF [CPF_") and len(first) == len("CPF [CPF_0123456789abcdef]")


def test_operator_per_label():
    result = Veu(operators={"CARTAO_CREDITO": "remover"}).anonymize("CPF 529.982.247-25 cartão 4111 1111 1111 1111")
    assert result.text == "CPF [CPF_1] cartão [CARTAO_CREDITO]"


def test_unknown_operator_is_rejected():
    with pytest.raises(ValueError, match="Operador desconhecido"):
        normalize_operator("criptografar")


def test_vault_round_trip_through_dict():
    result = veu.anonymize(TEXT)
    restored_vault = Vault.from_dict(json.loads(json.dumps(result.vault.to_dict())))
    assert restored_vault.restore("[PESSOA_1] / [EMAIL_1]") == "João da Silva / joao.silva@example.com"
    assert veu.anonymize("Outro CPF 111.444.777-35", restored_vault).text == "Outro CPF [CPF_2]"


def test_json_escape_for_tool_arguments():
    vault = Vault()
    vault.placeholder("PESSOA", 'Ana "Nina" Souza')
    assert vault.restore('{"nome": "[PESSOA_1]"}', json_escape=True) == '{"nome": "Ana \\"Nina\\" Souza"}'


def _stream(vault, text, sizes):
    restorer = vault.restorer()
    output, position = [], 0
    for size in sizes:
        output.append(restorer.feed(text[position:position + size]))
        position += size
    output.append(restorer.feed(text[position:]))
    output.append(restorer.flush())
    return "".join(output)


def test_streaming_restore_survives_every_split_point():
    result = veu.anonymize(TEXT)
    reply = "Olá [PESSOA_1]! CPF [CPF_1], telefone [TELEFONE_1], e-mail EMAIL_1. [link](https://x.y)"
    expected = result.restore(reply)
    for split in range(len(reply) + 1):
        assert _stream(result.vault, reply, [split]) == expected


def test_streaming_restore_with_random_chunks_and_synthetic_values():
    result = Veu(operator="sintetico").anonymize(TEXT)
    name = next(item.replacement for item in result.replacements if item.label == "PESSOA")
    reply = f"Prezado {name}, confirmamos. {name} pode ligar amanhã."
    expected = result.restore(reply)
    assert "João da Silva" in expected
    rng = random.Random(1)
    for _ in range(300):
        sizes = [rng.randint(1, 6) for _ in range(rng.randint(1, 20))]
        assert _stream(result.vault, reply, sizes) == expected
