"""Anonimização de DataFrames do pandas, com o mesmo marcador para o mesmo valor em todas as linhas.

    from veu.integrations.pandas import anonymize_dataframe, restore_dataframe

    anonimo, cofre = anonymize_dataframe(df, force={"cpf": "CPF"})
    # ... análise, envio para um modelo, compartilhamento ...
    original = restore_dataframe(anonimo, cofre)
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from veu.core import Veu
from veu.files import DataAnonymizer
from veu.vault import Vault


def _text_columns(df) -> list:
    import pandas as pd

    return [column for column in df.columns
            if pd.api.types.is_object_dtype(df[column]) or pd.api.types.is_string_dtype(df[column])]


def anonymize_dataframe(
    df,
    columns: Iterable | None = None,
    *,
    force: Mapping[str, str] | None = None,
    veu: Veu | None = None,
    vault: Vault | None = None,
):
    """Devolve (cópia anonimizada, cofre).

    columns: colunas analisadas (padrão: todas as colunas de texto).
    force: {coluna: TIPO} trata a coluna inteira como aquele dado, mesmo sem formato reconhecível.
    """
    session = (veu or Veu()).session(vault)
    force = dict(force or {})
    data = DataAnonymizer(session, force=force)
    output = df.copy()
    selected = list(columns) if columns is not None else _text_columns(df)
    for column in dict.fromkeys([*selected, *force]):
        if column not in output.columns:
            raise KeyError(f'Coluna "{column}" não existe no DataFrame.')
        output[column] = output[column].map(lambda value, name=column: data.value(name, value), na_action="ignore")
    return output, session.vault


def restore_dataframe(df, vault: Vault, columns: Iterable | None = None):
    """Devolve uma cópia com os dados reais no lugar dos marcadores."""
    output = df.copy()
    for column in list(columns) if columns is not None else _text_columns(df):
        output[column] = output[column].map(
            lambda value: vault.restore(value) if isinstance(value, str) else value, na_action="ignore"
        )
    return output
