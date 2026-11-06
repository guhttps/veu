"""Atalhos do Véu: área de trabalho, menu Iniciar e início junto com o computador (Windows, macOS e Linux).

    veu atalhos              # cria "Véu" na área de trabalho e no menu (abre o painel)
    veu atalhos --remover

O painel liga e desliga o início automático com set_autostart().
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from importlib import resources
from pathlib import Path

NAME = "Véu"


def veu_command() -> list[str]:
    """Como chamar o Véu instalado: o executável veu ao lado do Python atual, o do PATH ou python -m veu."""
    folder = Path(sys.executable).parent
    for candidate in (folder / "veu.exe", folder / "veu", folder / "Scripts" / "veu.exe"):
        if candidate.is_file():
            return [str(candidate)]
    found = shutil.which("veu")
    return [found] if found else [sys.executable, "-m", "veu"]


def icon_path() -> str:
    return str(resources.files("veu.server").joinpath("static", "veu.ico"))


def _powershell(script: str) -> str:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, check=False,
    )
    if result.returncode != 0:
        raise OSError(result.stderr.strip() or "Falha ao criar o atalho.")
    return result.stdout.strip()


def _ps(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _windows_folder(kind: str) -> Path:
    return Path(_powershell(f"[Environment]::GetFolderPath({_ps(kind)})"))


def _windows_shortcut(folder: str, arguments: str, *, minimized: bool = False, remove: bool = False) -> Path:
    """Cria (ou remove) Véu.lnk numa pasta especial do Windows (Desktop, Programs, Startup)."""
    target, *rest = veu_command()
    args = " ".join([*rest, arguments]).strip()
    script = f"""
$pasta = [Environment]::GetFolderPath({_ps(folder)})
$arquivo = Join-Path $pasta {_ps(NAME + '.lnk')}
if ({'$true' if remove else '$false'}) {{ if (Test-Path $arquivo) {{ Remove-Item $arquivo -Force }}; Write-Output $arquivo; exit 0 }}
$atalho = (New-Object -ComObject WScript.Shell).CreateShortcut($arquivo)
$atalho.TargetPath = {_ps(target)}
$atalho.Arguments = {_ps(args)}
$atalho.WorkingDirectory = [Environment]::GetFolderPath('UserProfile')
$atalho.IconLocation = {_ps(icon_path())}
$atalho.Description = 'Protege seus dados antes de usar IA'
$atalho.WindowStyle = {7 if minimized else 1}
$atalho.Save()
Write-Output $arquivo
"""
    return Path(_powershell(script))


def _shell_line(arguments: str) -> str:
    return " ".join(f'"{part}"' for part in veu_command()) + f" {arguments}"


def create_shortcuts(remove: bool = False) -> list[Path]:
    """Área de trabalho e menu do sistema. Devolve os arquivos criados (ou removidos)."""
    if sys.platform == "win32":
        return [_windows_shortcut(folder, "painel", remove=remove) for folder in ("Desktop", "Programs")]
    home = Path.home()
    if sys.platform == "darwin":
        targets = [home / "Desktop" / f"{NAME}.command", home / "Applications" / f"{NAME}.command"]
        content = f"#!/bin/sh\nexec {_shell_line('painel')}\n"
    else:
        targets = [home / ".local" / "share" / "applications" / "veu.desktop", home / "Desktop" / "veu.desktop"]
        content = (f"[Desktop Entry]\nType=Application\nName={NAME}\nComment=Protege seus dados antes de usar IA\n"
                   f"Exec={_shell_line('painel')}\nIcon={icon_path()}\nTerminal=true\nCategories=Utility;\n")
    done = []
    for target in targets:
        if remove:
            target.unlink(missing_ok=True)
        elif target.parent.is_dir() or target.parent.name == "applications":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            target.chmod(0o755)
        else:
            continue
        done.append(target)
    return done


def _autostart_file() -> Path:
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "LaunchAgents" / "io.github.guhttps.veu.plist"
    return Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "autostart" / "veu.desktop"


def autostart_enabled() -> bool:
    if sys.platform == "win32":
        try:
            return (_windows_folder("Startup") / f"{NAME}.lnk").is_file()
        except OSError:
            return False
    return _autostart_file().is_file()


def set_autostart(enabled: bool) -> None:
    """Liga ou desliga o Véu ao entrar no computador (sem abrir o navegador)."""
    if sys.platform == "win32":
        _windows_shortcut("Startup", "painel --sem-abrir", minimized=True, remove=not enabled)
        return
    file = _autostart_file()
    if not enabled:
        file.unlink(missing_ok=True)
        return
    file.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin":
        arguments = "".join(f"<string>{part}</string>" for part in [*veu_command(), "painel", "--sem-abrir"])
        file.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0"><dict>'
            "<key>Label</key><string>io.github.guhttps.veu</string>"
            f"<key>ProgramArguments</key><array>{arguments}</array>"
            "<key>RunAtLoad</key><true/></dict></plist>\n",
            encoding="utf-8",
        )
    else:
        file.write_text(f"[Desktop Entry]\nType=Application\nName={NAME}\nExec={_shell_line('painel --sem-abrir')}\n"
                        "X-GNOME-Autostart-enabled=true\n", encoding="utf-8")
