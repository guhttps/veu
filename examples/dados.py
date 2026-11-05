"""Anonimizar uma planilha antes de compartilhar ou de mandar para análise por IA.

    pip install "veu[pandas] @ git+https://github.com/guhttps/veu"
    python examples/dados.py
"""

import pandas as pd

from veu.integrations.pandas import anonymize_dataframe, restore_dataframe

clientes = pd.DataFrame({
    "nome": ["Joana Prado", "Carlos Lima", "Joana Prado"],
    "cpf": ["52998224725", "11144477735", "52998224725"],
    "observacao": ["ligar no (11) 91234-5678", "e-mail carlos@example.com", "cliente desde 2019"],
    "valor": [120.0, 89.9, 45.5],
})

# A coluna cpf não tem pontuação: "force" garante que ela seja tratada inteira como CPF.
anonimo, cofre = anonymize_dataframe(clientes, force={"cpf": "CPF"})
print(anonimo, end="\n\n")

# O mesmo cliente tem o mesmo marcador em todas as linhas: agrupar continua funcionando.
print(anonimo.groupby("cpf")["valor"].sum(), end="\n\n")

print(restore_dataframe(anonimo, cofre).equals(clientes))   # True
