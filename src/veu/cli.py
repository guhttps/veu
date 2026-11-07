"""Linha de comando do Véu."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from pathlib import Path

from veu import __version__
from veu.anonymizer import OPERATORS
from veu.config import ConfigError, load_config
from veu.core import Veu
from veu.entities import LABELS
from veu.files import FORMATS as FILE_FORMATS
from veu.reporting import REPORT_FORMATS
from veu.vault import Vault


def _configure_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _read(path: str | None) -> str:
    if path in (None, "-"):
        return sys.stdin.buffer.read().decode("utf-8", errors="replace")
    return Path(path).read_text(encoding="utf-8", errors="replace")


def _write(text: str, path: str | None) -> None:
    if path in (None, "-"):
        sys.stdout.write(text)
    else:
        Path(path).write_text(text, encoding="utf-8")


def _write_private(path: Path, text: str) -> None:
    """Grava um arquivo legível só pelo dono (no Linux e no macOS; no Windows vale a permissão da pasta)."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(text)
    with contextlib.suppress(OSError):
        os.chmod(path, 0o600)


def _veu(args) -> Veu:
    config = load_config(getattr(args, "config", None))
    overrides = {}
    if getattr(args, "limiar", None) is not None:
        overrides["threshold"] = args.limiar
    if getattr(args, "operador", None):
        overrides["operator"] = args.operador
    if getattr(args, "detectores", None):
        overrides["detectors"] = args.detectores.split(",")
    if getattr(args, "entidades", None):
        overrides["labels"] = [label.strip().upper() for label in args.entidades.split(",")]
    return Veu(config, **overrides) if overrides else Veu(config)


def cmd_detect(args) -> int:
    veu = _veu(args)
    results = []
    for path in args.arquivos or ["-"]:
        text = _read(path)
        for entity in veu.analyze(text):
            results.append({"arquivo": path if path != "-" else None, **entity.to_dict()})
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    elif not results:
        print("Nenhum dado pessoal encontrado.")
    else:
        for item in results:
            prefix = f"{item['arquivo']}: " if item["arquivo"] else ""
            print(f"{prefix}{item['entidade']:<16} {item['pontuacao']:.2f}  {item['texto']}")
    return 0


def _load_vault(path: str, args=None) -> Vault:
    from veu.config import load_config

    policy = load_config().restore_policy()
    if getattr(args, "restaurar_links", False):
        from dataclasses import replace

        policy = replace(policy, links=True)
    return Vault.from_dict(json.loads(Path(path).read_text(encoding="utf-8")), policy=policy)


def _parse_force(values: list[str] | None) -> dict[str, str]:
    """--forcar cpf=CPF --forcar nome=PESSOA -> {"cpf": "CPF", "nome": "PESSOA"}."""
    force = {}
    for item in values or []:
        for pair in item.split(","):
            if pair.strip():
                field, _, label = pair.partition("=")
                if not label:
                    raise ValueError(f'Use --forcar campo=TIPO (recebido "{pair}").')
                force[field.strip()] = label.strip().upper()
    return force


def _save_vault_and_report(args, session) -> None:
    if args.cofre:
        _write_private(Path(args.cofre), json.dumps(session.vault.to_dict(), ensure_ascii=False, indent=2))
        print(f"\nCofre salvo em {args.cofre}. Ele contém os dados reais: guarde com cuidado e não versione.",
              file=sys.stderr)
    if session.counts:
        summary = ", ".join(f"{label}={count}" for label, count in sorted(session.counts.items()))
        print(f"Escondidos: {summary}", file=sys.stderr)


def cmd_anonymize(args) -> int:
    from veu.documents import WRITABLE, read_document
    from veu.files import DataAnonymizer, anonymize_file, anonymize_text, detect_format

    veu = _veu(args)
    vault = _load_vault(args.cofre) if args.cofre and Path(args.cofre).is_file() and args.continuar else None
    session = veu.session(vault)
    path = Path(args.arquivo) if args.arquivo not in (None, "-") else None
    file_format = detect_format(path, args.formato)
    fields = [field.strip() for field in args.campos.split(",")] if args.campos else None
    force = _parse_force(args.forcar)
    if file_format in WRITABLE:
        if path is None or args.saida in (None, "-"):
            raise ValueError(f"Para {file_format}, informe o arquivo e a saída: "
                             f"veu anonimizar entrada.{file_format} -o protegido.{file_format}")
        _, counts = anonymize_file(path, args.saida, veu=veu, vault=session.vault, fields=fields, force=force)
        session.counts.update(counts)
        print(f"Documento protegido em {args.saida} (mesmo formato do original).", file=sys.stderr)
        _save_vault_and_report(args, session)
        return 0
    data = DataAnonymizer(session, fields, force)
    if file_format == "pdf":
        if path is None:
            raise ValueError("Informe o arquivo PDF.")
        text, file_format = read_document(path, "pdf"), "texto"
    else:
        text = _read(args.arquivo)
    _write(anonymize_text(text, file_format, data, path), args.saida)
    _save_vault_and_report(args, session)
    return 0


def cmd_restore(args) -> int:
    from veu.documents import WRITABLE
    from veu.files import detect_format, restore_file, restore_text

    path = Path(args.arquivo) if args.arquivo not in (None, "-") else None
    file_format = detect_format(path, args.formato)
    if file_format in WRITABLE:
        if path is None or args.saida in (None, "-"):
            raise ValueError(f"Para {file_format}, informe o arquivo e a saída (-o).")
        restore_file(path, args.saida, _load_vault(args.cofre, args))
        print(f"Documento restaurado em {args.saida}.", file=sys.stderr)
        return 0
    _write(restore_text(_read(args.arquivo), file_format, _load_vault(args.cofre, args)), args.saida)
    return 0


def cmd_read(args) -> int:
    """Lê uma fonte (Notion, Google, link ou documento) e mostra o conteúdo já protegido."""
    from veu.sources import SourceError, read_source

    veu = _veu(args)
    vault = _load_vault(args.cofre) if args.cofre and Path(args.cofre).is_file() and args.continuar else None
    try:
        document = read_source(args.fonte)
    except (SourceError, ImportError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2
    from veu.sources import protect_document

    session = veu.session(vault)
    title, text, counts = protect_document(document, session.anonymizer, session.vault)
    session.counts.update(counts)
    if args.json:
        output = {**document.to_dict(), "titulo": title, "texto": text, "escondidos": dict(session.counts)}
        _write(json.dumps(output, ensure_ascii=False, indent=2) + "\n", args.saida)
    else:
        _write(text if text.endswith("\n") else text + "\n", args.saida)
    _save_vault_and_report(args, session)
    return 0


def cmd_check(args) -> int:
    """Modo pre-commit/CI: lista dados pessoais em arquivos e falha se encontrar algum."""
    from veu.reporting import check_files, render

    findings, warnings = check_files(args.arquivos, _veu(args))
    for warning in warnings:
        print(warning, file=sys.stderr)
    report = render(findings, args.formato)
    if args.saida:
        Path(args.saida).write_text(report, encoding="utf-8")
    else:
        sys.stdout.write(report)
    for extra_format, path in (("sarif", args.sarif), ("json", args.json)):
        if path:
            Path(path).write_text(render(findings, extra_format), encoding="utf-8")
    if findings:
        print(f"\n{len(findings)} dado(s) pessoal(is) encontrado(s). Remova-os ou marque a linha com "
              "'# veu: ignorar'.", file=sys.stderr)
        return 0 if args.nao_falhar else 1
    return 0


def cmd_hook(args) -> int:
    """Gancho para agentes de código (Claude Code, Cursor): lê o evento em JSON da entrada padrão."""
    from veu.entities import SECRET_LABELS
    from veu.hooks import run

    block = frozenset(label.strip().upper() for label in args.bloquear.split(",")) if args.bloquear else SECRET_LABELS
    return run(args.evento, mode=args.modo, pii=args.dados_pessoais, block=block, fmt=args.formato, veu=_veu(args))


def cmd_audit(args) -> int:
    """Confere a cadeia de hashes de um log de auditoria do servidor."""
    from veu.server.state import verify_audit

    secret = os.environ.get(args.segredo_env) if args.segredo_env else None
    if args.segredo_env and not secret:
        raise ValueError(f"A variável {args.segredo_env} não está definida.")
    ok, count, problem = verify_audit(args.arquivo, secret)
    if ok:
        print(f"Log íntegro: {count} registros, cadeia completa.")
        return 0
    print(f"Log comprometido depois de {count} registros válidos: {problem}.", file=sys.stderr)
    return 1


def cmd_demo(args) -> int:
    from veu.demo import run

    return run()


def cmd_mcp(args) -> int:
    try:
        from veu.integrations.mcp import build_server
    except ImportError:
        print('O servidor MCP precisa do extra: pip install "veu[mcp]"', file=sys.stderr)
        return 2
    build_server(_veu(args), restore_text=args.com_restauracao).run("stdio")
    return 0


def cmd_serve(args) -> int:
    try:
        from veu.server import app as server
    except ImportError:
        print('O servidor precisa das dependências extras: pip install "veu[servidor]"', file=sys.stderr)
        return 2
    config = load_config(args.config)
    overrides = {}
    if args.host:
        overrides["host"] = args.host
    if args.porta:
        overrides["port"] = args.porta
    config = config.with_overrides(**overrides) if overrides else config
    server.run(config)
    return 0


def cmd_panel(args) -> int:
    try:
        from veu.server import app as server
    except ImportError:
        print('O painel precisa do servidor: pip install "veu[servidor]"', file=sys.stderr)
        return 2
    server.run_panel(open_browser=not args.sem_abrir, port=args.porta)
    return 0


def cmd_shortcuts(args) -> int:
    from veu.atalhos import create_shortcuts

    for path in create_shortcuts(remove=args.remover):
        print(("Removido: " if args.remover else "Atalho: ") + str(path))
    return 0


def cmd_evaluate(args) -> int:
    from veu.bench.desafio import challenge_samples
    from veu.bench.evaluate import evaluate
    from veu.bench.generator import generate, load
    from veu.bench.hard import hard_samples

    veu = _veu(args)
    external = {}
    if args.externo:
        from veu.bench.external import TEST_SETS, load_external

        names = list(TEST_SETS) if args.externo == "todos" else [args.externo]
        sets = {}
        for name in names:
            samples, skipped, dataset = load_external(name, args.limite)
            sets[name] = samples
            external[name] = (skipped, dataset)
    elif args.dataset:
        sets = {"arquivo": load(args.dataset)}
    else:
        sets = {
            "desenvolvimento": generate(args.quantidade, args.semente),
            "validacao": generate(args.quantidade, args.semente + 1, validation=True),
            "dificeis": hard_samples(),
            # Escrito à mão e congelado: mede a generalização, não é usado para ajustar os detectores.
            "desafio": challenge_samples(),
        }
    reports = {name: evaluate(samples, veu) for name, samples in sets.items()}
    for name, (skipped, _) in external.items():
        reports[name].out_of_scope = dict(skipped)
    if args.json:
        print(json.dumps({name: report.to_dict() for name, report in reports.items()}, ensure_ascii=False, indent=2))
    else:
        for name, report in reports.items():
            speed = report.to_dict()["caracteres_por_segundo"]
            print(f"\n## Conjunto: {name} ({report.samples} textos, {speed} caracteres/s)\n")
            if name in external:
                dataset = external[name][1]
                print(f"{dataset.title}, licença {dataset.license}: {dataset.page}\n")
            print(report.to_markdown(precision=name not in external))
    if args.max_vazamento is not None:
        # O desafio mostra onde o Véu ainda erra; o limite vale para os outros conjuntos (com os gerados, o que
        # importa é a validação, que o ajuste dos detectores não vê).
        gated = [report for name, report in reports.items() if name not in ("desafio", "desenvolvimento")]
        worst = max(report.overall.leak_rate for report in gated)
        if worst > args.max_vazamento:
            print(f"\nVazamento {worst:.2%} acima do máximo permitido ({args.max_vazamento:.2%}).", file=sys.stderr)
            return 1
    return 0


def cmd_generate(args) -> int:
    from veu.bench.generator import generate, save

    samples = generate(args.quantidade, args.semente, validation=args.validacao)
    save(samples, args.saida)
    print(f"{len(samples)} textos salvos em {args.saida}", file=sys.stderr)
    return 0


def cmd_entities(args) -> int:
    for label, description in LABELS.items():
        print(f"{label:<16} {description}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="veu", description="Esconde dados pessoais e segredos antes de enviar textos para modelos de IA.",
    )
    parser.add_argument("--versao", "--version", action="version", version=f"veu {__version__}")
    commands = parser.add_subparsers(dest="comando", required=True, metavar="comando")

    def common(sub):
        sub.add_argument("--config", help="caminho do veu.toml")
        sub.add_argument("--limiar", type=float, help="pontuação mínima de 0 a 1 (padrão 0,5)")
        sub.add_argument("--detectores", help="lista separada por vírgula: padroes,nomes,enderecos,segredos,spacy,llm")
        sub.add_argument("--entidades", help="limita a alguns tipos, como CPF,EMAIL")

    sub = commands.add_parser("detectar", help="lista os dados pessoais encontrados")
    sub.add_argument("arquivos", nargs="*", help="arquivos de texto (padrão: entrada padrão)")
    sub.add_argument("--json", action="store_true", help="saída em JSON")
    common(sub)
    sub.set_defaults(func=cmd_detect)

    sub = commands.add_parser("ler", help="lê Notion, Google Docs/Sheets, um link ou um documento já protegido")
    sub.add_argument("fonte", help="URL do Notion, do Google ou de uma página, ou arquivo (docx, xlsx, pptx, pdf...)")
    sub.add_argument("--cofre", help="salva o cofre neste JSON para restaurar a resposta da IA depois")
    sub.add_argument("--continuar", action="store_true", help="reaproveita o cofre existente (marcadores estáveis)")
    sub.add_argument("--operador", choices=sorted(OPERATORS), help="como substituir (padrão: token)")
    sub.add_argument("--json", action="store_true", help="saída em JSON com título, tipo e contagens")
    sub.add_argument("-o", "--saida", help="arquivo de saída (padrão: saída padrão)")
    common(sub)
    sub.set_defaults(func=cmd_read)

    sub = commands.add_parser("anonimizar", help="troca os dados pessoais por marcadores")
    sub.add_argument("arquivo", nargs="?", help="arquivo (texto, CSV, JSON, Word, Excel, PowerPoint ou PDF)")
    sub.add_argument("--operador", choices=sorted(OPERATORS), help="como substituir (padrão: token)")
    sub.add_argument("--cofre", help="salva o cofre neste JSON para restaurar depois")
    sub.add_argument("--continuar", action="store_true", help="reaproveita o cofre existente (marcadores estáveis)")
    sub.add_argument("--formato", choices=FILE_FORMATS,
                     help="texto, csv, json, jsonl, docx, xlsx, pptx ou pdf (padrão: pela extensão)")
    sub.add_argument("--campos", help="só estas colunas/chaves, separadas por vírgula")
    sub.add_argument("--forcar", action="append", metavar="CAMPO=TIPO",
                     help="trata o campo inteiro como um tipo de dado (ex.: cpf=CPF); pode repetir")
    sub.add_argument("-o", "--saida", help="arquivo de saída (padrão: saída padrão)")
    common(sub)
    sub.set_defaults(func=cmd_anonymize)

    sub = commands.add_parser("restaurar", help="devolve os dados reais usando um cofre salvo")
    sub.add_argument("arquivo", nargs="?", help="arquivo de texto (padrão: entrada padrão)")
    sub.add_argument("--cofre", required=True, help="cofre salvo pelo comando anonimizar")
    sub.add_argument("--formato", choices=FILE_FORMATS,
                     help="texto, csv, json, jsonl, docx, xlsx ou pptx (padrão: pela extensão)")
    sub.add_argument("-o", "--saida", help="arquivo de saída (padrão: saída padrão)")
    sub.add_argument("--restaurar-links", action="store_true",
                     help="restaura também dentro de links e URLs (por padrão eles continuam com os marcadores)")
    sub.set_defaults(func=cmd_restore)

    sub = commands.add_parser("verificar", help="falha se algum arquivo tiver dados pessoais (pre-commit, CI)")
    sub.add_argument("arquivos", nargs="+")
    sub.add_argument("--formato", choices=REPORT_FORMATS, default="texto",
                     help="texto, github (anotações no CI), sarif (aba Security do GitHub) ou json")
    sub.add_argument("--saida", help="grava o relatório neste arquivo")
    sub.add_argument("--sarif", metavar="ARQUIVO", help="também grava um relatório SARIF neste arquivo")
    sub.add_argument("--json", metavar="ARQUIVO", help="também grava um relatório JSON neste arquivo")
    sub.add_argument("--nao-falhar", action="store_true", help="sai com código 0 mesmo encontrando dados")
    common(sub)
    sub.set_defaults(func=cmd_check)

    sub = commands.add_parser("gancho", help="gancho para Claude Code e Cursor (prompt e leitura de arquivos)")
    sub.add_argument("evento", choices=("prompt", "arquivo"),
                     help="prompt: antes de enviar o prompt; arquivo: antes de o agente ler um arquivo")
    sub.add_argument("--modo", choices=("avisar", "bloquear"), default="avisar",
                     help="prompt com dados pessoais (que não são segredos): avisar (padrão) ou bloquear")
    sub.add_argument("--dados-pessoais", choices=("permitir", "perguntar", "negar"), default="perguntar",
                     help="arquivo com dados pessoais: permitir, perguntar (padrão) ou negar a leitura")
    sub.add_argument("--bloquear", help="tipos que sempre bloqueiam (padrão: segredos, como CHAVE_API,SENHA)")
    sub.add_argument("--formato", choices=("claude", "cursor"), default="claude", help="formato do agente")
    common(sub)
    sub.set_defaults(func=cmd_hook)

    sub = commands.add_parser("demonstrar", help="mostra, sem chave de API, o que chega à IA com e sem o Véu")
    sub.set_defaults(func=cmd_demo)

    sub = commands.add_parser("auditoria", help="confere a integridade do log de auditoria do servidor")
    sub.add_argument("acao", choices=("verificar",))
    sub.add_argument("arquivo", help="log de auditoria (JSONL)")
    sub.add_argument("--segredo-env", help="variável de ambiente com o segredo da auditoria (se configurado)")
    sub.set_defaults(func=cmd_audit)

    sub = commands.add_parser("mcp", help="servidor MCP (stdio) para Claude Code, Claude Desktop, Cursor...")
    common(sub)
    sub.add_argument("--com-restauracao", action="store_true",
                     help="inclui restaurar_texto, que devolve os dados reais para a conversa com a IA")
    sub.set_defaults(func=cmd_mcp)

    sub = commands.add_parser("painel", help="liga o Véu e abre o painel no navegador (o jeito mais fácil)")
    sub.add_argument("--porta", type=int, help="porta (padrão 8787)")
    sub.add_argument("--sem-abrir", action="store_true", help="não abre o navegador (para iniciar com o computador)")
    sub.set_defaults(func=cmd_panel)

    sub = commands.add_parser("atalhos", help="cria o atalho Véu na área de trabalho e no menu")
    sub.add_argument("--remover", action="store_true", help="remove os atalhos")
    sub.set_defaults(func=cmd_shortcuts)

    sub = commands.add_parser("servir", help="inicia o proxy e o playground")
    sub.add_argument("--config", help="caminho do veu.toml")
    sub.add_argument("--host")
    sub.add_argument("--porta", type=int)
    sub.set_defaults(func=cmd_serve)

    sub = commands.add_parser("avaliar", help="mede precisão, revocação e vazamento no benchmark")
    sub.add_argument("--dataset", help="arquivo JSONL (padrão: conjuntos gerados)")
    sub.add_argument("--quantidade", type=int, default=1000)
    sub.add_argument("--semente", type=int, default=42)
    sub.add_argument("--json", action="store_true")
    sub.add_argument("--max-vazamento", type=float,
                     help="falha se o vazamento da validação (ou do conjunto escolhido) passar deste valor (0 a 1)")
    sub.add_argument("--externo", choices=("br-agentic", "privacy-filter-br", "privacy-filter-br-treino", "todos"),
                     help="conjunto público de terceiros, baixado uma vez (versão fixa, conferida pelo sha256); "
                          "todos = os dois de teste")
    sub.add_argument("--limite", type=int, help="usa só as primeiras N amostras do conjunto externo")
    common(sub)
    sub.set_defaults(func=cmd_evaluate)

    sub = commands.add_parser("gerar-dataset", help="gera textos anotados com dados falsos (JSONL)")
    sub.add_argument("--quantidade", type=int, default=1000)
    sub.add_argument("--semente", type=int, default=42)
    sub.add_argument("--validacao", action="store_true", help="usa os modelos do conjunto de validação")
    sub.add_argument("-o", "--saida", required=True)
    sub.set_defaults(func=cmd_generate)

    sub = commands.add_parser("entidades", help="lista os tipos de dados detectados")
    sub.set_defaults(func=cmd_entities)
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_output()
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, ValueError, FileNotFoundError, ImportError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
