# -*- coding: utf-8 -*-
"""
TESTE AUTOMÁTICO — rode com:  python testar_sem_planilha.py

Não precisa de internet, de planilha do Google nem dos seus vídeos: cria uma
pasta de vídeo fictícia na pasta temporária do Windows, roda a busca inteira e
confere se o resultado é o esperado. Serve para saber se o Python e o script
funcionam na máquina antes de apontar para o servidor de verdade.

Nada é gravado fora da pasta temporária, e nada é apagado do seu computador.
"""

import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

# O config.py não vai junto no git, então num clone novo ele ainda não existe.
# Aqui só precisamos de EXTENSOES_VIDEO; usamos o exemplo como base.
if not (RAIZ / "config.py").exists():
    (RAIZ / "config.py").write_text(
        (RAIZ / "config.exemplo.py").read_text(encoding="utf-8"), encoding="utf-8"
    )
    print("  (aviso: config.py criado a partir do exemplo para este teste)\n")

import config  # noqa: E402
import buscar_placas as bp  # noqa: E402

# (nome do arquivo, placas que ele deve casar)
# São 8 vídeos que casam ou não + 1 em subpasta = 9 arquivos de vídeo,
# e 1 .txt que nunca pode entrar na lista.
CASOS = [
    ("FIAT STRADA-ABC-1234 - STORY.mp4", {"ABC1234"}),
    ("onix-abc1234-manha-2.mov",        {"ABC1234"}),
    ("ONIX-ABC-1234 (1).avi",           {"ABC1234"}),
    ("subpasta/VW-ABC-1234-interior.mkv", {"ABC1234"}),
    ("FIAT STRADA ABC 1D23.mp4",        {"ABC1D23"}),
    ("ZZZZ-DEF4G56-fim.mp4",            {"DEF4G56"}),
    ("XYZ9A87 parte final.mp4",         {"XYZ9A87"}),
    ("video_ADC1234X_final.mp4",         set()),   # placa colada: NÃO deve casar
    ("sem-nada-a-ver-aqui.mp4",         set()),
]

NAO_VIDEO = "nota-de-video.txt"

PLACAS = {"ABC1234", "ABC1D23", "DEF4G56", "XYZ9A87"}
TOTAL_VIDEOS = 9
TOTAL_COPIADOS = 7


def montar_cenario(diretorio):
    """Cria a pasta de vídeos fictícia e devolve o caminho dela."""
    videos = diretorio / "videos"
    (videos / "subpasta").mkdir(parents=True, exist_ok=True)

    for nome, _ in CASOS:
        caminho = videos / nome
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_bytes(b"conteudo ficticio do video")

    (videos / NAO_VIDEO).write_text("isto nao e um video", encoding="utf-8")
    return videos


def main():
    print("=" * 62)
    print("  TESTE AUTOMATICO - buscar placas")
    print("=" * 62)
    print("\n  Python: %s" % sys.version.split()[0])
    print("  Pasta : %s\n" % RAIZ)

    temporaria = Path(tempfile.mkdtemp(prefix="teste_placas_"))
    try:
        videos = montar_cenario(temporaria)
        resultados = temporaria / "resultados"
        matcher = bp.MatcherPlacas(PLACAS)

        falhas = []

        # --- 1) o nome dos arquivos casa com a placa certa? --------------
        print("  [1] Reconhecendo placas no nome dos arquivos")
        for nome, esperado in CASOS:
            obtido = matcher(nome)
            certo = obtido == esperado
            if not certo:
                falhas.append("nome %s: esperava %s, obtive %s"
                              % (nome, sorted(esperado), sorted(obtido)))
            print("      %s %-38s -> %s" % (
                "OK  " if certo else "FALHA", nome, sorted(obtido) or "(nenhuma)"))

        # --- 2) a varredura acha os vídeos e ignora o .txt ---------------
        print("\n  [2] Varrendo a pasta")
        encontrados = bp.achar_videos(videos, config.EXTENSOES_VIDEO, True, set())
        achou_txt = any(c.name == NAO_VIDEO for c in encontrados)
        certo = len(encontrados) == TOTAL_VIDEOS and not achou_txt
        if len(encontrados) != TOTAL_VIDEOS:
            falhas.append("varredura achou %d, esperado %d"
                          % (len(encontrados), TOTAL_VIDEOS))
        if achou_txt:
            falhas.append("a varredura incluiu %s, que não é vídeo" % NAO_VIDEO)
        print("      %s %d video(s) encontrado(s) (esperado %d)"
              % ("OK  " if certo else "FALHA", len(encontrados), TOTAL_VIDEOS))
        print("      %s %s ignorado (não é vídeo)"
              % ("OK  " if not achou_txt else "FALHA", NAO_VIDEO))

        # --- 3) a cópia cria a estrutura certa? --------------------------
        print("\n  [3] Copiando os videos")
        resultado, copias, _, _ = bp.varrer_e_copiar(
            encontrados, matcher, resultados, False, False
        )
        certo = copias == TOTAL_COPIADOS
        if not certo:
            falhas.append("copiou %d, esperado %d" % (copias, TOTAL_COPIADOS))
        print("      %s %d video(s) copiado(s) (esperado %d)"
              % ("OK  " if certo else "FALHA", copias, TOTAL_COPIADOS))

        for placa, quantidade in [("ABC1234", 4), ("ABC1D23", 1), ("DEF4G56", 1), ("XYZ9A87", 1)]:
            achado = len(resultado.get(placa, []))
            certo = achado == quantidade
            if not certo:
                falhas.append("pasta %s: %d video(s), esperado %d" % (placa, achado, quantidade))
            print("      %s %s/ tem %d video(s) (esperado %d)"
                  % ("OK  " if certo else "FALHA", placa, achado, quantidade))

        # --- 4) o conteudo copiado bate com o original? ------------------
        print("\n  [4] Conferindo o conteudo das copias")
        erros = 0
        for pasta in resultados.iterdir():
            if not pasta.is_dir():
                continue
            for copia in pasta.iterdir():
                original = videos / copia.name
                if not original.exists():
                    original = videos / "subpasta" / copia.name
                if not original.exists():
                    erros += 1
                elif original.read_bytes() != copia.read_bytes():
                    erros += 1
        if erros:
            falhas.append("%d copia(s) com conteudo diferente do original" % erros)
        print("      %s %d arquivo(s) com conteudo diferente (esperado 0)"
              % ("OK  " if erros == 0 else "FALHA", erros))

        # --- 5) rodar duas vezes nao duplica nada ------------------------
        print("\n  [5] Rodando de novo (nao deve duplicar)")
        _, copias2, _, _ = bp.varrer_e_copiar(
            encontrados, matcher, resultados, False, False
        )
        certo = copias2 == 0
        if not certo:
            falhas.append("2a rodada copiou %d, esperado 0" % copias2)
        print("      %s %d copia(s) na 2a rodada (esperado 0)"
              % ("OK  " if certo else "FALHA", copias2))

    finally:
        shutil.rmtree(temporaria, ignore_errors=True)

    print("\n" + "=" * 62)
    if falhas:
        print("  FALHOU (%d):" % len(falhas))
        for falha in falhas:
            print("    - %s" % falha)
        print("=" * 62)
        return 1

    print("  TUDO OK - o script funciona nesta maquina.")
    print("")
    print("  Proximo passo:")
    print("      1. Abra o config.py e preencha as 3 linhas (URL_PLANILHA,")
    print("         PASTA_VIDEOS e PASTA_RESULTADOS)")
    print("      2. python buscar_placas.py --simular")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
