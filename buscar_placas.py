# -*- coding: utf-8 -*-
"""
BUSCAR PLACAS EM VÍDEOS
=======================

Fluxo:

    Google Sheets  ->  lê todas as placas
    Vídeos do PC   ->  procura cada placa no nome dos arquivos
    Encontrou?     ->  copia o vídeo para RESULTADOS/PLACA/

Exemplo de estrutura gerada:

    📁 RESULTADOS
       ├── ABC1D23
       │   ├── FIAT STRADA-ABC1D23 - STORY.mp4
       │   └── video_02.mp4
       ├── XYZ9A87
       │   └── video_15.mp4
       └── DEF4G56
           └── video_22.mp4

Uso:
    python buscar_placas.py                  # usa o config.py
    python buscar_placas.py --simular        # só mostra o que faria
    python buscar_placas.py --videos "D:\\" --resultados "D:\\OUT"
    python buscar_placas.py --planilha placas_exemplo.csv
"""

import argparse
import csv
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from placas import MatcherPlacas
from planilha import ErroPlanilha, ler_placas

try:
    import config
except ImportError:  # evita traceback feio se faltar o config.py
    # O config.py fica de fora do git de propósito (o .gitignore), porque tem o
    # link da planilha. Então é normal precisar criá-lo logo após clonar.
    print("ERRO: config.py não encontrado.\n")
    print("Ele não vai junto no git, porque tem o link da sua planilha.")
    print("Crie o seu a partir do exemplo:\n")
    print("    copy config.exemplo.py config.py")
    print()
    print("Depois abra o config.py e preencha URL_PLANILHA, PASTA_VIDEOS e")
    print("PASTA_RESULTADOS. É o único arquivo que você precisa editar.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Log
# ---------------------------------------------------------------------------


def _configurar_saida():
    """Impede UnicodeEncodeError no console do Windows (cp1252/cp850).

    Sem isso, imprimir um acento ou o emoji de pasta estoura com
    "UnicodeEncodeError: 'charmap' codec can't encode character".
    """
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleOutputCP(65001)  # UTF-8 na saída
            ctypes.windll.kernel32.SetConsoleCP(65001)  # UTF-8 na entrada
        except Exception:  # pragma: no cover - depende do terminal
            pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


_configurar_saida()

_COR = {
    "VERDE": "\033[32m",
    "VERMELHO": "\033[31m",
    "AMARELO": "\033[33m",
    "CIANO": "\033[36m",
    "CINZA": "\033[90m",
    "NEGRITO": "\033[1m",
    "FIM": "\033[0m",
}

_USAR_COR = sys.stdout.isatty() and os.name != "nt" or bool(
    os.environ.get("WT_SESSION") or os.environ.get("TERM_PROGRAM")
)


def _pintar(texto, cor):
    return "%s%s%s" % (_COR[cor], texto, _COR["FIM"]) if _USAR_COR else texto


def info(mensagem):
    print(_pintar(mensagem, "CIANO"))


def ok(mensagem):
    print(_pintar("  [OK] " + mensagem, "VERDE"))


def aviso(mensagem):
    print(_pintar("  [!] " + mensagem, "AMARELO"))


def erro(mensagem):
    print(_pintar("  [X] " + mensagem, "VERMELHO"))


def detalhe(mensagem):
    if config.NIVEL_LOG.upper() == "DEBUG":
        print(_pintar("      " + mensagem, "CINZA"))


def titulo(mensagem):
    print()
    print(_pintar(mensagem, "NEGRITO"))


# ---------------------------------------------------------------------------
# Varredura de vídeos
# ---------------------------------------------------------------------------


def _chave(caminho):
    """Chave de comparação de caminhos, sem tocar no disco.

    Não usa Path.resolve() de propósito: em caminho UNC, resolve() faz I/O de
    rede para cada componente do caminho, e o script chama isso uma vez por
    arquivo. abspath() e normcase() são só string, sem I/O.
    """
    return os.path.normcase(os.path.abspath(str(caminho)))


def achar_videos(pasta, extensoes, recursivo, ignoradas, excluir=None):
    """Lista recursivamente os arquivos de vídeo da pasta."""
    # Barra final para \\srv\resultados não casar com \\srv\resultados-antigos
    prefixo_excluir = (_chave(excluir) + os.sep) if excluir else ""
    encontrados = []

    padrao = "**/*" if recursivo else "*"
    for caminho in sorted(pasta.glob(padrao)):
        # A extensão vem primeiro: é só string e já descarta a maioria dos
        # diretórios, evitando um stat (ida ao servidor) para cada um.
        if caminho.suffix.lower() not in extensoes:
            continue
        if prefixo_excluir and (_chave(caminho) + os.sep).startswith(prefixo_excluir):
            detalhe("dentro da pasta de destino, ignorando: %s" % caminho.name)
            continue
        if ignoradas & set(caminho.parts):
            continue
        if not caminho.is_file():
            continue
        encontrados.append(caminho)

    return encontrados


def achar_videos_completo(pasta, excluir=None):
    """Segunda passada: ignora PASTAS_IGNORADAS e o filter de extensão."""
    return achar_videos(
        pasta,
        tuple(e.lower() for e in config.EXTENSOES_VIDEO),
        config.BUSCAR_RECURSSIVO,
        set(config.PASTAS_IGNORADAS),
        excluir,
    )


# ---------------------------------------------------------------------------
# Cópia
# ---------------------------------------------------------------------------


def nome_destino(caminho_original, destino_pasta, indice, padrao_video_n):
    """Define o nome do arquivo dentro da pasta da placa."""
    if padrao_video_n:
        return destino_pasta / ("video_%02d%s" % (indice, caminho_original.suffix.lower()))
    return destino_pasta / caminho_original.name


def tamanho_legivel(arquivo):
    """'245.3 MB' — ajuda a ver o progresso em vídeos grandes."""
    try:
        megabytes = arquivo.stat().st_size / (1024 * 1024)
    except OSError:
        return "?"
    if megabytes < 1:
        return "%.0f KB" % (megabytes * 1024)
    if megabytes < 1024:
        return "%.1f MB" % megabytes
    return "%.2f GB" % (megabytes / 1024)


def _copiar_arquivo(origem, destino, buffer_bytes):
    """Copia em blocos grandes, tolerando falha ao ajustar metadados.

    Usa shutil.copy2 porque ele copia em blocos de 1 MB (64 KB em alguns
    sistemas), o que fica lento em vídeo grande vindo da rede, e porque o
    copystat dele pode estourar em alguns compartilhamentos SMB.

    Aqui o bloco é configurável e o copystat é "melhor esforço": se o servidor
    recusar ajustar a data do arquivo, os bytes já estão no destino e isso não
    deve ser tratado como falha de cópia.
    """
    with open(origem, "rb") as arquivo_origem, open(destino, "wb") as arquivo_destino:
        shutil.copyfileobj(arquivo_origem, arquivo_destino, buffer_bytes)

    try:
        shutil.copystat(origem, destino)
    except OSError:
        pass  # metadados são acessório; os dados já foram gravados


def copiar(video, destino_pasta, indice, sobrescrever):
    """Copia o vídeo e devolve (sucesso, caminho_final, motivo_da_pular)."""
    destino = nome_destino(video, destino_pasta, indice, config.NOMEAR_POR_PADRAO_VIDEO_N)

    if destino.exists():
        if not sobrescrever:
            return False, destino, "já existe"
        try:
            destino.unlink()
        except OSError as excecao:
            return False, destino, "não consegui sobrescrever (%s)" % excecao

    try:
        destino_pasta.mkdir(parents=True, exist_ok=True)
    except OSError as excecao:
        return False, destino, "não consegui criar a pasta (%s)" % excecao

    try:
        _copiar_arquivo(video, destino, config.TAMANHO_BUFFER_MB * 1024 * 1024)
    except (OSError, PermissionError) as excecao:
        # Arquivo pela metade não pode sobrar: confundiria a próxima rodada.
        try:
            destino.unlink()
        except OSError:
            pass
        return False, destino, "falha na cópia (%s)" % excecao

    return True, destino, ""


def eh_unc(caminho):
    r"""É um caminho de rede (\\servidor\pasta)?"""
    return str(caminho).startswith(("\\\\", "//"))


def caminho_relativo(destino, pasta_resultados):
    """Mostra o destino relativo à pasta de resultados, sem quebrar se estiver fora."""
    try:
        return destino.relative_to(pasta_resultados)
    except ValueError:
        return destino


# ---------------------------------------------------------------------------
# Relatório
# ---------------------------------------------------------------------------


def gerar_relatorio(resultados, pasta_resultados, elapsed):
    """Salva relatorio.csv e um resumo em texto."""
    encontrados = {p: v for p, v in resultados.items() if v}
    ausentes = [p for p, v in resultados.items() if not v]

    caminho_csv = pasta_resultados / "relatorio.csv"
    with open(caminho_csv, "w", newline="", encoding="utf-8-sig") as arquivo:
        escritor = csv.writer(arquivo, delimiter=";")
        escritor.writerow(["PLACA", "SITUACAO", "QTD_VIDEOS", "VIDEO(S)"])
        for placa in sorted(resultados):
            videos = resultados[placa]
            escritor.writerow([
                placa,
                "ENCONTRADA" if videos else "NAO ENCONTRADA",
                len(videos),
                " | ".join(videos),
            ])

    caminho_txt = pasta_resultados / "relatorio.txt"
    with open(caminho_txt, "w", encoding="utf-8") as arquivo:
        arquivo.write("RELATORIO - BUSCAR PLACAS\n")
        arquivo.write("Gerado em: %s\n" % datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
        arquivo.write("Placas lidas:      %d\n" % len(resultados))
        arquivo.write("Placas encontradas: %d\n" % len(encontrados))
        arquivo.write("Placas ausentes:    %d\n" % len(ausentes))
        arquivo.write("Videos copiados:    %d\n" % sum(len(v) for v in resultados.values()))
        arquivo.write("Tempo total:        %.1fs\n" % elapsed)
        arquivo.write("\n" + "=" * 60 + "\n\n")

        for placa in sorted(encontrados):
            arquivo.write("%s  (%d video(s))\n" % (placa, len(resultados[placa])))
            for video in resultados[placa]:
                arquivo.write("    - %s\n" % video)
            arquivo.write("\n")

        if ausentes:
            arquivo.write("PLACAS NAO ENCONTRADAS (%d)\n" % len(ausentes))
            arquivo.write("-" * 60 + "\n")
            for placa in sorted(ausentes):
                arquivo.write("    %s\n" % placa)

    return caminho_csv, caminho_txt


# ---------------------------------------------------------------------------
# Núcleo
# ---------------------------------------------------------------------------


def varrer_e_copiar(videos, matcher, pasta_resultados, sobrescrever, simulando):
    """Relaciona vídeos x placas e copia os que casarem.

    Devolve (resultados, copias, ja_existiam, encontrados) onde:
      - resultados:    {placa: [nomes dos vídeos]}  ← o que casou na busca
      - copias:         quantos arquivos foram gravados nesta rodada
      - ja_existiam:   quantos já estavam no destino e foram pulados
      - encontrados:   quantos pares (vídeo, placa) casaram
    """
    resultados = {placa: [] for placa in matcher.placas}
    copias = 0
    ja_existiam = 0
    encontrados = 0

    for numero, video in enumerate(videos, 1):
        achadas = matcher(video.name)

        if not achadas:
            detalhe("sem placa: %s" % video.name)
            continue

        for placa in sorted(achadas):
            encontrados += 1
            destino_pasta = pasta_resultados / placa
            indice = len(resultados[placa]) + 1

            # O achado é registrado sempre, mesmo que o arquivo já exista no
            # destino: senão a 2ª rodada diria "placa não encontrada".
            resultados[placa].append(video.name)

            if simulando:
                destino = nome_destino(video, destino_pasta, indice, config.NOMEAR_POR_PADRAO_VIDEO_N)
                print("  %s %s  ->  %s" % (
                    _pintar("[SIMULA]", "AMARELO"),
                    video.name,
                    caminho_relativo(destino, pasta_resultados),
                ))
                continue

            sucesso, destino, motivo = copiar(video, destino_pasta, indice, sobrescrever)
            if not sucesso:
                ja_existiam += 1
                aviso("%s em %s: %s" % (video.name, placa, motivo))
                continue

            print("  %s %s (%s)  ->  %s" % (
                _pintar("[OK]", "VERDE"),
                video.name,
                tamanho_legivel(video),
                caminho_relativo(destino, pasta_resultados),
            ))
            copias += 1

        if numero % 50 == 0:
            print(_pintar("    ... %d/%d vídeos analisados" % (numero, len(videos)), "CINZA"))

    return resultados, copias, ja_existiam, encontrados


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def montar_parser():
    parser = argparse.ArgumentParser(
        description="Lê placas do Google Sheets e copia os vídeos correspondentes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemplos:\n"
            "  python buscar_placas.py --simular\n"
            "  python buscar_placas.py --videos \"D:\\Videos\" --resultados \"D:\\OUT\"\n"
            "  python buscar_placas.py --planilha placas_exemplo.csv\n"
        ),
    )
    parser.add_argument("--videos", help="Pasta com os vídeos (sobrescreve o config.py)")
    parser.add_argument("--resultados", help="Pasta de destino (sobrescreve o config.py)")
    parser.add_argument("--url", help="Link/ID/caminho da planilha")
    parser.add_argument("--planilha", help="Lê de um CSV local em vez do Google Sheets")
    parser.add_argument("--coluna", help="Coluna das placas (nome ou índice). Ex.: 0")
    parser.add_argument("--tolerante", action="store_true",
                        help="Placa não precisa estar isolada no nome do arquivo")
    parser.add_argument("--sobrescrever", action="store_true",
                        help="Sobrescreve arquivos que já existem no destino")
    parser.add_argument("--simular", action="store_true",
                        help="Dry-run: mostra o que seria copiado, sem copiar nada")
    parser.add_argument("--debug", action="store_true", help="Log detalhado")
    return parser


def resolver_coluna(valor):
    if valor is None:
        return None
    valor = str(valor).strip()
    return int(valor) if valor.isdigit() else valor


def main():
    args = montar_parser().parse_args()
    if args.debug:
        config.NIVEL_LOG = "DEBUG"
    if args.tolerante:
        config.MATCH_TOLERANTE = True
    if args.sobrescrever:
        config.SOBRESCREVER = True

    pasta_videos = Path(args.videos or config.PASTA_VIDEOS).expanduser()
    pasta_resultados = Path(args.resultados or config.PASTA_RESULTADOS).expanduser()
    origem_planilha = args.planilha or args.url or config.URL_PLANILHA

    # ---------------------------------------------------------------- valida
    titulo("1) Validando configuracao")

    # Junta todos os problemas para mostrar de uma vez, em vez de descobrir
    # um erro por execução.
    problemas = []

    if args.videos or args.resultados:
        origem_videos = args.videos or config.PASTA_VIDEOS
        if not str(origem_videos).strip():
            problemas.append("PASTA_VIDEOS está vazia no config.py.")
    if not pasta_videos.exists():
        if eh_unc(pasta_videos):
            problemas.append(
                "Não consegui acessar o compartilhamento de rede: %s\n"
                "      Teste o mesmo caminho no Explorer. Se não abrir, é share\n"
                "      fora do ar ou faltando credencial neste PC.\n"
                r"      Para reconectar:  net use \\SERVIDOR\Pasta /user:USUARIO"
                % pasta_videos
            )
        else:
            problemas.append("Pasta de vídeos não encontrada: %s" % pasta_videos)
    elif not pasta_videos.is_dir():
        problemas.append("Isso não é uma pasta: %s" % pasta_videos)

    if not str(origem_planilha).strip():
        problemas.append("URL_PLANILHA está vazia no config.py.")
    elif "COLE_AQUI" in str(origem_planilha).upper():
        problemas.append(
            "URL_PLANILHA ainda é o texto de exemplo.\n"
            "      Abra o config.py e cole o link da planilha do Google Sheets."
        )

    if problemas:
        for problema in problemas:
            erro(problema)
        print("\n  Corrija o arquivo config.py (é o único que você precisa editar).")
        return 1

    ok("Pasta de vídeos:   %s" % pasta_videos)
    ok("Pasta de destino:  %s" % pasta_resultados)

    if args.simular:
        info("MODO SIMULAÇÃO: nada será copiado.")
    else:
        try:
            pasta_resultados.mkdir(parents=True, exist_ok=True)
        except OSError as excecao:
            erro("Não consegui criar a pasta de destino (%s)" % excecao)
            return 1

    # -------------------------------------------------------------- planilha
    titulo("2) Lendo as placas da planilha")
    try:
        placas = ler_placas(origem_planilha, resolver_coluna(args.coluna or config.COLUNA_PLANILHA))
    except ErroPlanilha as excecao:
        erro(str(excecao))
        return 1
    ok("%d placas únicas carregadas" % len(placas))
    detalhe("exemplos: %s" % ", ".join(sorted(placas)[:5]))

    # --------------------------------------------------------------- vídeos
    titulo("3) Varrendo os vídeos")
    videos = achar_videos_completo(pasta_videos, excluir=pasta_resultados)
    if not videos:
        erro("Nenhum arquivo de vídeo encontrado em %s" % pasta_videos)
        aviso("Extensões configuradas: %s" % ", ".join(config.EXTENSOES_VIDEO))
        return 1
    ok("%d vídeos encontrados" % len(videos))

    # ------------------------------------------------------- copiar / simular
    titulo("4) Procurando placas%s" % (" (MODO TOLERANTE)" if config.MATCH_TOLERANTE else ""))
    inicio = datetime.now()
    matcher = MatcherPlacas(placas, config.MATCH_TOLERANTE)
    resultados, copias, ja_existiam, encontrados = varrer_e_copiar(
        videos, matcher, pasta_resultados, config.SOBRESCREVER, args.simular
    )
    elapsed = (datetime.now() - inicio).total_seconds()

    # Se NENHUM par (vídeo, placa) casou, vale tentar o modo tolerante.
    # O teste é em "encontrados", não em "copias": numa segunda rodada os
    # arquivos já estão no destino e "copias" é 0 mesmo tendo encontrado tudo.
    if encontrados == 0 and not config.MATCH_TOLERANTE:
        aviso("Nada encontrado no modo normal. Refazendo em modo tolerante...")
        matcher = MatcherPlacas(placas, tolerante=True)
        resultados, copias, ja_existiam, _ = varrer_e_copiar(
            videos, matcher, pasta_resultados, config.SOBRESCREVER, args.simular
        )
        if copias:
            aviso("O modo tolerante pode gerar falsos positivos. Confira o relatório.")

    # -------------------------------------------------------------- resumo
    encontradas = [p for p, v in resultados.items() if v]
    ausentes = [p for p, v in resultados.items() if not v]

    titulo("5) Resumo")
    print("  Placas na planilha:   %d" % len(placas))
    print("  Encontradas:          %d  %s" % (len(encontradas), _pintar("OK", "VERDE")))
    print("  Não encontradas:      %d  %s" % (len(ausentes), _pintar("FALTA", "AMARELO")))
    print("  Vídeos copiados:      %d%s" % (
        copias,
        "  (%d já existiam no destino)" % ja_existiam if ja_existiam else "",
    ))
    print("  Tempo:                %.1fs" % elapsed)

    if ausentes:
        preview = ", ".join(sorted(ausentes)[:12])
        print("\n  Sem vídeo: %s%s" % (preview, " ..." if len(ausentes) > 12 else ""))

    if copias and not args.simular:
        print("\n  📁 %s" % pasta_resultados)
        for placa in sorted(encontradas)[:8]:
            print("     ├── %s/  (%d)" % (placa, len(resultados[placa])))
        if len(encontradas) > 8:
            print("     └── ... mais %d pastas" % (len(encontradas) - 8))

    if config.GERAR_RELATORIO and not args.simular:
        csv_path, txt_path = gerar_relatorio(resultados, pasta_resultados, elapsed)
        print("\n  Relatórios: %s | %s" % (csv_path.name, txt_path.name))

    print()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrompido pelo usuário.")
        sys.exit(130)
