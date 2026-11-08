"""
title: Véu
author: guhttps
author_url: https://github.com/guhttps/veu
funding_url: https://github.com/guhttps/veu
version: 0.6.0
license: MIT
description: Esconde dados pessoais e segredos (CPF, nomes, e-mails, chaves de API...) antes de a mensagem ir ao modelo e devolve os dados reais na resposta.
requirements: veu>=0.6.0
"""

# Cole este arquivo em Painel do administrador > Funções > Criar, no Open WebUI.
# O filtro em si fica no pacote veu: veja veu/integrations/openwebui.py.
from veu.integrations.openwebui import Filter  # noqa: F401
