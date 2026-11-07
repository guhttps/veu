# Instalador do Veu para Windows. Nao precisa de administrador nem de Python instalado.
#
# Abra o PowerShell (tecla Windows, digite PowerShell, Enter) e cole:
#     irm https://guhttps.github.io/veu/instalar.ps1 | iex
#
# O que ele faz:
#   1. instala o uv (gerenciador de Python da Astral), se ainda nao houver;
#   2. instala o Veu com o painel, o suporte a Excel/Word/PDF e o servidor MCP;
#   3. cria o atalho "Veu" na area de trabalho e no menu Iniciar e abre o painel.
# Para desinstalar: uv tool uninstall veu (e apague o atalho).
& {
    # Sem "Stop": no PowerShell 5.1, ele trataria como erro fatal qualquer aviso que o uv escreve (como o progresso
    # do download). Cada passo confere o resultado.
    $ErrorActionPreference = "Continue"
    $ProgressPreference = "SilentlyContinue"
    $pacote = if ($env:VEU_PACOTE) { $env:VEU_PACOTE } else { "veu[servidor,mcp,documentos]" }

    function Passo([string] $texto) { Write-Host ""; Write-Host "  $texto" -ForegroundColor Cyan }
    function Falhou([string] $texto) {
        Write-Host ""
        Write-Host "  $texto" -ForegroundColor Red
        Write-Host "  Se precisar de ajuda: https://github.com/guhttps/veu/issues"
        throw "Instalacao do Veu interrompida."
    }

    Write-Host ""
    Write-Host "  Instalando o Veu: protecao de dados para IA" -ForegroundColor Green

    Passo "1 de 3: preparando o Python (uv)..."
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        try {
            Invoke-RestMethod https://astral.sh/uv/install.ps1 -ErrorAction Stop | Invoke-Expression
        } catch {
            Falhou "Nao consegui baixar o uv. Confira a internet e tente de novo. ($_)"
        }
        $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
    }
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { Falhou "Nao consegui instalar o uv." }

    Passo "2 de 3: instalando o Veu (pode levar um minuto)..."
    uv tool install --force --refresh-package veu --python 3.13 $pacote
    if ($LASTEXITCODE -ne 0) { Falhou "Nao consegui instalar o Veu." }
    uv tool update-shell *> $null
    $veu = Join-Path ((uv tool dir --bin) | Out-String).Trim() "veu.exe"
    if (-not (Test-Path $veu)) { Falhou "O Veu foi instalado, mas nao encontrei o programa em $veu." }

    Passo "3 de 3: criando o atalho Veu na area de trabalho..."
    if (-not $env:VEU_SEM_ATALHO) { & $veu atalhos | Out-Null }

    Write-Host ""
    Write-Host "  Pronto! O Veu esta instalado." -ForegroundColor Green
    Write-Host "  O painel vai abrir no navegador. Depois, para abrir de novo, use o atalho Veu na area de trabalho."
    Write-Host ""
    if (-not $env:VEU_SEM_ABRIR) { Start-Process -FilePath $veu -ArgumentList "painel" }
}
