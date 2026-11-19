"""Extensão: padrões seguros e o pacote do Firefox."""

import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXTENSION = ROOT / "extensao"


def test_real_data_in_the_page_is_opt_in():
    """Na página, o código do site também leria os dados reais: a restauração na tela vem desligada."""
    assert re.search(r"restaurarRespostas: false", (EXTENSION / "fundo.js").read_text(encoding="utf-8"))
    assert re.search(r"restaurarRespostas: false", (EXTENSION / "conteudo.js").read_text(encoding="utf-8"))


def test_content_script_runs_before_the_page():
    manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["content_scripts"][0]["run_at"] == "document_start"


def test_manifest_fits_the_store_limits():
    # A Chrome Web Store e a loja do Edge recusam o pacote se a descrição passar de 132 caracteres. O nome e a
    # descrição vêm de _locales, um arquivo por idioma; todo idioma precisa das duas mensagens.
    manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "__MSG_extensionName__" and manifest["description"] == "__MSG_extensionDescription__"
    locales = {path.parent.name: json.loads(path.read_text(encoding="utf-8"))
               for path in (EXTENSION / "_locales").glob("*/messages.json")}
    assert {"en", "pt_BR"} <= set(locales) and manifest["default_locale"] in locales
    for messages in locales.values():
        assert len(messages["extensionName"]["message"]) <= 75
        assert len(messages["extensionDescription"]["message"]) <= 132


def test_content_script_recognizes_hash_placeholders():
    source = (EXTENSION / "conteudo.js").read_text(encoding="utf-8")
    pattern = re.search(r"const PLACEHOLDER = /(.+)/;", source).group(1).replace("\\\\", "\\")
    assert re.search(pattern, "[CPF_3fa2c1d9e07b4a12]")


def _packager():
    import importlib.util

    spec = importlib.util.spec_from_file_location("empacotar", ROOT / "scripts" / "empacotar_navegador.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_package_includes_every_language(tmp_path):
    if not (EXTENSION / "veu.global.js").exists():
        return  # o pacote só se monta depois de scripts/empacotar_navegador.py
    manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
    output = tmp_path / "pacote.zip"
    _packager().write_zip(output, manifest)
    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
    assert {"_locales/en/messages.json", "_locales/pt_BR/messages.json"} <= names


def test_firefox_manifest():
    module = _packager()
    manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
    firefox = module.firefox_manifest(manifest)
    assert firefox["background"] == {"scripts": ["fundo.js"]}
    assert firefox["browser_specific_settings"]["gecko"]["id"] == "veu@guhttps.github.io"
    assert "minimum_chrome_version" not in firefox and firefox["version"] == manifest["version"]
    # A Mozilla recusa extensões novas que não declaram se coletam dados.
    assert firefox["browser_specific_settings"]["gecko"]["data_collection_permissions"] == {"required": ["none"]}


def test_zips_when_built(tmp_path):
    dist = ROOT / "dist"
    zips = sorted(dist.glob("veu-extensao-firefox-*.zip")) if dist.exists() else []
    if not zips:
        return  # o pacote só existe depois de scripts/empacotar_navegador.py
    with zipfile.ZipFile(zips[-1]) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("manifest.json"))
    assert {"manifest.json", "conteudo.js", "fundo.js", "veu.global.js"} <= names
    assert "scripts" in manifest["background"]


SERVICE_WORKER_HARNESS = r"""
const fs = require("fs"), vm = require("vm");
const store = { sync: {}, session: {} };
const area = (name) => ({
  get: async (key) => (key === null ? { ...store[name] } : { [key]: store[name][key] }),
  set: async (values) => { Object.assign(store[name], values); },
  remove: async () => {},
  setAccessLevel: () => {},
});
let listener;
const event = () => ({ addListener: (fn) => { listener ??= fn; } });
const chrome = {
  storage: { managed: { get: async () => ({}) }, sync: area("sync"), session: area("session") },
  runtime: { onMessage: { addListener: (fn) => { listener = fn; } }, onInstalled: event(),
             getURL: (path) => "chrome-extension://veu/" + path },
  tabs: { onRemoved: event() }, contextMenus: { onClicked: event() },
  action: { setBadgeBackgroundColor: async () => {}, setBadgeText: async () => {} },
};
vm.runInNewContext(fs.readFileSync(process.argv[1], "utf8"), { chrome, console });
const send = (sender) => new Promise((resolve) =>
  listener({ tipo: "salvarPreferencias", preferencias: { ativo: false } }, sender, resolve));
(async () => {
  const fromPage = await send({ tab: { id: 7 }, url: "https://chatgpt.com/" });
  const afterPage = store.sync.ativo ?? null;
  const fromPopup = await send({ id: "veu", url: "chrome-extension://veu/popup.html", tab: { id: 8 } });
  console.log(JSON.stringify({ fromPage, afterPage, fromPopup: fromPopup.ativo, afterPopup: store.sync.ativo }));
})();
"""


def test_only_the_popup_changes_preferences():
    """O script que roda dentro dos sites de IA não consegue desligar a proteção pelo service worker."""
    import shutil
    import subprocess

    if not shutil.which("node"):
        import pytest

        pytest.skip("precisa do Node")
    result = subprocess.run(["node", "-e", SERVICE_WORKER_HARNESS, str(EXTENSION / "fundo.js")],
                            capture_output=True, text=True, encoding="utf-8", check=True)
    data = json.loads(result.stdout)
    assert "erro" in data["fromPage"] and data["afterPage"] is None
    assert data["fromPopup"] is False and data["afterPopup"] is False
