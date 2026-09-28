# -*- coding: utf-8 -*-
"""
Regras de normalização e comparação de placas Brazilianas.

Ideia central: a planilha é a fonte da verdade. O script NÃO tenta adivinhar
placas em qualquer texto; ele só verifica se alguma placa que está na planilha
aparece no nome do vídeo. Isso elimina a maioria dos falsos positivos.
"""

import re
import unicodedata

# Separadores viram espaço (mantém as "fronteiras" das palavras).
_RE_SEPARADORES = re.compile(r"[^A-Z0-9]+")

# Separadores aceitos entre os grupos da placa: espaço, traço, ponto, etc.
_SEP = r"[\s\-\._\u2010\u2011\u2012\u2013\u2014_]?"

# Placas no padrão Mercosul: ABC1D23 (3 letras, dígito, letra, 2 dígitos)
_RE_MERCOSUL = re.compile(
    r"(?<![A-Z0-9])([A-Z]{3})" + _SEP + r"([0-9])" + _SEP + r"([A-Z])" + _SEP + r"([0-9]{2})(?![A-Z0-9])"
)

# Placas no padrão antigo: ABC1234 / ABC-1234
_RE_ANTIGA = re.compile(
    r"(?<![A-Z0-9])([A-Z]{3})" + _SEP + r"([0-9]{4})(?![A-Z0-9])"
)

# Remove espaços, pontos, traços e afins: "abc-1d23" -> "ABC1D23"
_RE_NAO_ALNUM = re.compile(r"[^A-Z0-9]+")


def limpar_texto(valor):
    """Normaliza texto para comparação: maiúsculas, sem acento, sem pontuação.

    >>> limpar_texto("Fiat Strada-ABC-1234")
    'FIAT STRADA ABC 1234'
    """
    if valor is None:
        return ""
    texto = unicodedata.normalize("NFKD", str(valor))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return _RE_SEPARADORES.sub(" ", texto.upper()).strip()


def normalizar_placa(valor):
    """Vira a placa em uma chave única de 7 caracteres, sem separadores.

    >>> normalizar_placa("abc-1234")
    'ABC1234'
    >>> normalizar_placa("ABC1D23")
    'ABC1D23'
    """
    return _RE_NAO_ALNUM.sub("", limpar_texto(valor))


def extrair_placas(valor):
    """Pega todas as placas de uma célula da planilha.

    Aceita células sujas como "ABC-1234 (Fiat Strada)" ou "placa: abc 1d23".

    >>> sorted(extrair_placas("ABC-1234 / DEF5G67"))
    ['ABC1234', 'DEF5G67']
    """
    texto = limpar_texto(valor)
    if not texto:
        return set()

    encontradas = set()
    for letra, digito, letra_meio, finais in _RE_MERCOSUL.findall(texto):
        encontradas.add(letra + digito + letra_meio + finais)
    for letra, numeros in _RE_ANTIGA.findall(texto):
        encontradas.add(letra + numeros)
    return encontradas


def _corpo_do_padrao(placa):
    """Gera o corpo do regex de uma placa, com os caracteres literais.

    A placa chega normalizada e sem separadores ('ABC1D23'), mas no nome do
    arquivo ela pode aparecer com traço, espaço ou nada: 'ABC-1D23', 'ABC 1D23',
    'ABC1D23'. Então cada caractere vira literal e os vãos entre eles aceitam
    um separador opcional.

    Os caracteres precisam ser LITERAIS (e não [A-Z]/[0-9]): se fossem classes,
    qualquer placa com o mesmo formato casaria com qualquer outra.

    >>> _corpo_do_padrao("ABC1D23")
    'A[SEP]?B[SEP]?C[SEP]?1[SEP]?D[SEP]?2[SEP]?3'
    """
    partes = []
    for indice, caractere in enumerate(placa):
        if indice:
            partes.append(_SEP + "?")
        partes.append(re.escape(caractere))
    return "".join(partes)


def _regex_do_lote(placas):
    """Compila um regex único de alternância para um lote de placas."""
    corpo = "|".join(_corpo_do_padrao(p) for p in placas)
    return re.compile(r"(?<![A-Z0-9])(?:%s)(?![A-Z0-9])" % corpo)


def placa_esta_no_nome(placa, nome_normalizado, tolerante=False):
    """A placa aparece no nome já normalizado do arquivo?

    Em modo normal a placa precisa estar "isolada" (não colada em outras
    letras/números), evitando que 'ABC1234' case dentro de 'ADC1234X'.
    """
    if not placa or len(placa) < 7:
        return False
    if tolerante:
        return placa in nome_normalizado.replace(" ", "")
    return bool(_regex_do_lote([placa]).search(nome_normalizado))


def placas_no_nome(nome_arquivo, placas, tolerante=False):
    """Devolve as placas conhecidas que aparecem no nome do arquivo.

    >>> placas_no_nome("FIAT STRADA-ABC-1234 - STORY.mp4", {"ABC1234"})
    {'ABC1234'}
    """
    placas = set(placas)
    nome_normalizado = limpar_texto(nome_arquivo)
    if not placas or not nome_normalizado:
        return set()

    if tolerante:
        compacto = nome_normalizado.replace(" ", "")
        return {p for p in placas if p in compacto}

    return {
        p for p in placas if _regex_do_lote([p]).search(nome_normalizado)
    }


class MatcherPlacas:
    """Reaproveita os regex compilados para varrer milhares de vídeos.

    Compilar um regex por placa e por arquivo é caro; aqui os regex são
    montados uma única vez, em lotes, e reaproveitados.
    """

    _TAMANHO_LOTE = 2000

    def __init__(self, placas, tolerante=False):
        self.placas = {p for p in placas if len(p) >= 7}
        self.tolerante = tolerante
        self._lotes = [
            _regex_do_lote(lote)
            for lote in self._dividir(self.placas)
        ] if not tolerante else []

    @classmethod
    def _dividir(cls, placas):
        placas = sorted(placas)
        return [
            placas[i:i + cls._TAMANHO_LOTE]
            for i in range(0, len(placas), cls._TAMANHO_LOTE)
        ]

    def __call__(self, nome_arquivo):
        nome_normalizado = limpar_texto(nome_arquivo)
        if not self.placas or not nome_normalizado:
            return set()

        if self.tolerante:
            compacto = nome_normalizado.replace(" ", "")
            return {p for p in self.placas if p in compacto}

        encontradas = set()
        for regex in self._lotes:
            for achado in regex.findall(nome_normalizado):
                # findall devolve a alternativa que casou, já com os separadores
                # do nome; basta remover os separadores para voltar à chave.
                encontradas.add(_RE_NAO_ALNUM.sub("", achado))
        return encontradas & self.placas
