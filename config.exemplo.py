# -*- coding: utf-8 -*-
"""
Configuração central do "buscar placas".

>>> EDITE APENAS ESTE ARQUIVO <<<

Tudo que você precisa mudar para o script rodar está aqui: link da
planilha, pasta dos vídeos e pasta de destino.
"""

# ---------------------------------------------------------------------------
# 1) PLANILHA DO GOOGLE SHEETS
# ---------------------------------------------------------------------------

# Cole aqui o link da planilha. O script aceita vários formatos e converte
# sozinho para o export CSV:
#
#   https://docs.google.com/spreadsheets/d/ID/edit#gid=0
#   https://docs.google.com/spreadsheets/d/ID/edit?gid=123
#   https://docs.google.com/spreadsheets/d/ID/export?format=csv
#   https://docs.google.com/spreadsheets/d/ID/gviz/tq?tqx=out:csv
#   https://docs.google.com/spreadsheets/d/ID/pub?output=csv
#   1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms        <- só o ID
#
# IMPORTANTE: a planilha precisa estar compartilhada como
#   "Qualquer pessoa com o link > Leitor".
URL_PLANILHA = "COLE_AQUI_O_LINK_DA_PLANILHA"

# Nome (ou índice) da coluna que tem as placas.
#   None -> detecção automática (recomendado)
#   "PLACA" / "placa" / 0 / 1 ...
COLUNA_PLANILHA = None


# ---------------------------------------------------------------------------
# 2) PASTAS
# ---------------------------------------------------------------------------

# Pasta onde estão os vídeos a serem analisados.
# Aceita caminho local (C:\Videos) OU caminho de rede (\\SERVIDOR\Videos).
# Para rede, deixar o destino em disco local costuma ser bem mais rápido.
PASTA_VIDEOS = r"C:\Users\Administrator\Videos\buscar"

# Pasta onde os vídeos encontrados serão copiados.
# Se estiver dentro de PASTA_VIDEOS, ela é ignorada na varredura
# (o script nunca processa a própria saída).
PASTA_RESULTADOS = r"C:\Users\Administrator\Videos\RESULTADOS"


# ---------------------------------------------------------------------------
# 3) VÍDEOS
# ---------------------------------------------------------------------------

EXTENSOES_VIDEO = (
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v",
    ".mpg", ".mpeg", ".wmv", ".flv", ".ts", ".3gp",
)

# Entrar em subpastas da PASTA_VIDEOS? (True = varre tudo recursivamente)
BUSCAR_RECURSSIVO = True

# True  -> os vídeos são salvos como video_01.mp4, video_02.mp4, ...
# False -> mantém o nome original do arquivo (recomendado, evita confusão)
NOMEAR_POR_PADRAO_VIDEO_N = False

# Subpastas com esses nomes são puladas durante a varredura
PASTAS_IGNORADAS = {"node_modules", "$RECYCLE.BIN", "System Volume Information"}


# ---------------------------------------------------------------------------
# 4) COMPORTAMENTO DO MATCH
# ---------------------------------------------------------------------------

# A placa precisa aparecer "isolada" no nome do arquivo, isto é, sem letras
# ou números colados nela.
#
#   "FIAT STRADA-ABC-1234 - STORY.mp4"   -> casa (ABC-1234 está isolada)
#   "video_ADC1234X_final.mp4"           -> não casa (colada em outros chars)
#
# Se NENHUM vídeo for encontrado, o script avisa e refaz a busca em modo
# tolerante (sem exigir o isolamento). Só mexer aqui se quiser usar sempre
# esse modo tolerante, que pode gerar falsos positivos.
MATCH_TOLERANTE = False

# Sobrescrever arquivos que já existem no destino?
SOBRESCREVER = False

# Tamanho do bloco de leitura na cópia, em MB.
# Vídeos grandes vindos da rede copiam bem mais rápido com blocos grandes.
# Se der erro de memória ou a rede travar, baixe para 1.
TAMANHO_BUFFER_MB = 4

# Gerar relatorio.csv + relatorio.txt na pasta de resultados?
GERAR_RELATORIO = True


# ---------------------------------------------------------------------------
# 5) LOG
# ---------------------------------------------------------------------------

# "INFO"  -> mostra tudo
# "DEBUG" -> mostra também os vídeos ignorados
NIVEL_LOG = "INFO"
