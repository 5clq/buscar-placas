# -*- coding: utf-8 -*-
"""
Leitura das placas direto do Google Sheets, sem dependências externas.

O script converte o link que você colou no config.py para o endpoint oficial
de exportação CSV e baixa o conteúdo com a biblioteca padrão do Python.
"""

import csv
import io
import re
import urllib.error
import urllib.request

from placas import extrair_placas

_RE_ID_PLANILHA = re.compile(r"/spreadsheets/d/([a-zA-Z0-9-_]+)")
_RE_GID = re.compile(r"[#?&]gid=([0-9]+)")

# O gviz responde com uma página HTML (200 OK) quando não tem permissão.
_MARCA_HTML = re.compile(r"<\s*(!doctype|html|head|body)\b", re.IGNORECASE)


class ErroPlanilha(Exception):
    """Erro de configuração ou de acesso à planilha."""


def _extrair_id_e_gid(link):
    """Aceita link completo ou ID solto e devolve (id, gid|None)."""
    link = link.strip()
    if not link:
        raise ErroPlanilha("URL_PLANILHA está vazia no config.py.")

    gid = _RE_GID.search(link)
    numero_gid = gid.group(1) if gid else None

    # 1) Link de planilha, com ou sem "https://" e com o caminho que for.
    achado = _RE_ID_PLANILHA.search(link)
    if achado:
        return achado.group(1), numero_gid

    # 2) ID solto, com ou sem "#gid=..." grudado.
    id_sozinho = re.split(r"[#?]", link, 1)[0].strip()
    if re.fullmatch(r"[a-zA-Z0-9-_]{20,}", id_sozinho):
        return id_sozinho, numero_gid

    raise ErroPlanilha(
        "Não consegui localizar o ID da planilha no link informado.\n"
        f"    Recebido: {link}\n"
        "    Use o link do navegador (ex.: https://docs.google.com/spreadsheets/d/<ID>/edit)\n"
        "    ou cole apenas o ID da planilha."
    )


def montar_url_csv(link):
    """Transforma qualquer link válido do Sheets em uma URL de export CSV."""
    id_planilha, gid = _extrair_id_e_gid(link)
    base = f"https://docs.google.com/spreadsheets/d/{id_planilha}/export?format=csv"
    return f"{base}&gid={gid}" if gid else base


def baixar_csv(url, timeout=60):
    """Baixa o CSV e devolve o texto decodificado."""
    requisicao = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (buscar-placas)"},
    )
    try:
        with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:
            dados = resposta.read()
    except urllib.error.HTTPError as erro:
        if erro.code in (401, 403):
            raise ErroPlanilha(
                "A planilha recusou o acesso (erro %s).\n"
                "No Google Sheets, clique em Compartilhar > Acesso para\n"
                "'Qualquer pessoa com o link' > Leitor, e tente de novo."
                % erro.code
            ) from erro
        if erro.code == 404:
            raise ErroPlanilha(
                "Planilha não encontrada (erro 404). Confira o link no config.py."
            ) from erro
        raise ErroPlanilha(
            "Erro %s ao acessar a planilha: %s" % (erro.code, erro.reason)
        ) from erro
    except urllib.error.URLError as erro:
        raise ErroPlanilha(
            "Não consegui acessar a internet: %s\n"
            "Confira sua conexão." % erro.reason
        ) from erro

    for codec in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            texto = dados.decode(codec)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ErroPlanilha("Não consegui decodificar o conteúdo da planilha.")

    if _MARCA_HTML.search(texto):
        raise ErroPlanilha(
            "O Google devolveu uma página HTML em vez do CSV.\n"
            "Normalmente isso significa que a planilha está privada.\n"
            "Compartilhe como 'Qualquer pessoa com o link > Leitor'."
        )
    return texto


def ler_linhas(texto_csv):
    """Converte o texto CSV em uma lista de linhas."""
    try:
        return list(csv.reader(io.StringIO(texto_csv), delimiter=";"))
    except csv.Error:
        return list(csv.reader(io.StringIO(texto_csv), delimiter=","))


def escolher_coluna(linhas, coluna_configurada=None):
    """Descobre em qual coluna estão as placas.

    Se `coluna_configurada` for informado (nome ou índice), usa direto.
    Caso contrário, pontua cada coluna pela quantidade de células que
    parecem placas e escolhe a melhor.
    """
    if not linhas:
        raise ErroPlanilha("A planilha está vazia.")

    if coluna_configurada is not None:
        if isinstance(coluna_configurada, int):
            indice = coluna_configurada
        else:
            alvo = str(coluna_configurada).strip().lower()
            indice = next(
                (
                    i
                    for i, cabecalho in enumerate(linhas[0])
                    if cabecalho.strip().lower() == alvo
                ),
                None,
            )
            if indice is None:
                raise ErroPlanilha(
                    "COLUNA_PLANILHA = %r não existe na planilha.\n"
                    "Colunas encontradas na primeira linha: %s"
                    % (coluna_configurada, [c for c in linhas[0] if c])
                )
        if indice >= len(linhas[0]):
            raise ErroPlanilha(
                "COLUNA_PLANILHA aponta para a coluna %d, que não existe." % indice
            )
        return indice

    largura = max(len(linha) for linha in linhas)
    melhor_indice, melhor_pontuacao = 0, -1
    for coluna in range(largura):
        pontuacao = sum(
            len(extrair_placas(linha[coluna])) for linha in linhas if len(linha) > coluna
        )
        if pontuacao > melhor_pontuacao:
            melhor_indice, melhor_pontuacao = coluna, pontuacao

    if melhor_pontuacao == 0:
        raise ErroPlanilha(
            "Nenhuma placa foi reconhecida na planilha.\n"
            "Esperado algo como 'ABC-1234' ou 'ABC1D23'.\n"
            "Se as placas estiverem em outra coluna, defina COLUNA_PLANILHA no config.py."
        )
    return melhor_indice


def ler_placas(link, coluna=None):
    """Ponto de entrada: devolve um set de placas normalizadas (ex.: {'ABC1234'})."""
    if link.lower().endswith(".csv") and not link.startswith(("http://", "https://")):
        with open(link, "r", encoding="utf-8-sig", errors="replace") as arquivo:
            linhas = list(csv.reader(arquivo, delimiter=";"))
    else:
        linhas = ler_linhas(baixar_csv(montar_url_csv(link)))

    indice = escolher_coluna(linhas, coluna)

    placas = set()
    for linha in linhas:
        if len(linha) > indice:
            placas.update(extrair_placas(linha[indice]))

    if not placas:
        raise ErroPlanilha(
            "A coluna %d da planilha não tem nenhuma placa válida." % indice
        )
    return placas
