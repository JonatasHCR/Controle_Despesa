"""Graficos do painel, em SVG gerado no servidor. Sem biblioteca e sem JS.

Uma cor so por grafico: ambos sao serie unica comparando magnitude, e colorir
por categoria faria a cor mudar de dono a cada mudanca de ranking. A cor vem de
token CSS para acompanhar a troca de tema.

Toda marca leva o valor escrito. Barra sem numero ate compara duas categorias
entre si, mas nao permite medir nenhuma delas.
"""

from __future__ import annotations

from decimal import Decimal
from html import escape

from markupsafe import Markup

from app.formato import moeda

COR = "var(--viz-serie)"

RAIO = 4
FOLGA = 6
ALTURA_BARRA = 22
LARGURA_ROTULO = 168
MARGEM_VALOR = 104
MAXIMO_CATEGORIAS = 8
LIMITE_ROTULO = 26

# Espaco no topo do grafico de colunas para o valor caber acima da marca.
TOPO_VALOR = 20
ALTURA_EIXO = 22


def barras_horizontais(
    dados: list[tuple[str, Decimal]],
    *,
    titulo: str = "",
    largura: int = 620,
    maximo: int = MAXIMO_CATEGORIAS,
) -> Markup:
    """Barras horizontais, da maior para a menor.

    Horizontal porque os nomes sao longos ("SERVICOS ESPECIALIZADOS MEI").
    """
    itens = _dobrar_cauda(sorted(dados, key=lambda par: par[1], reverse=True), maximo)
    if not itens:
        return _sem_dados()

    maior = max((valor for _, valor in itens), default=Decimal(0))
    util = largura - LARGURA_ROTULO - MARGEM_VALOR
    altura = len(itens) * (ALTURA_BARRA + FOLGA) + FOLGA

    partes = [_abertura(largura, altura, titulo, itens)]
    for indice, (rotulo, valor) in enumerate(itens):
        y = FOLGA + indice * (ALTURA_BARRA + FOLGA)
        comprimento = _proporcao(valor, maior) * util
        meio = y + ALTURA_BARRA / 2 + 4

        partes.append(
            f'<text class="rotulo" x="0" y="{meio:.0f}" '
            f'font-size="12">{escape(_encurtar(rotulo))}</text>'
        )
        partes.append(
            f'<rect class="marca" x="{LARGURA_ROTULO}" y="{y}" '
            f'width="{comprimento:.1f}" height="{ALTURA_BARRA}" '
            f'rx="{RAIO}" fill="{COR}">'
            f"<title>{escape(rotulo)}: {escape(moeda(valor))}</title>"
            f"</rect>"
        )
        partes.append(
            f'<text class="valor" x="{LARGURA_ROTULO + comprimento + 8:.0f}" '
            f'y="{meio:.0f}" font-size="12">{escape(moeda(valor))}</text>'
        )

    partes.append("</svg>")
    return Markup("".join(partes))


def colunas(
    dados: list[tuple[str, Decimal]],
    *,
    titulo: str = "",
    largura: int = 460,
    altura: int = 220,
) -> Markup:
    """Colunas verticais na ordem em que chegam, com o valor acima de cada uma.

    Nao ordena: e serie temporal, e reordenar por valor poria julho antes de
    marco.
    """
    itens = list(dados)
    if not itens:
        return _sem_dados()

    maior = max((valor for _, valor in itens), default=Decimal(0))
    base = altura - ALTURA_EIXO
    disponivel = base - TOPO_VALOR
    passo = largura / len(itens)
    espessura = max(10.0, min(46.0, passo - FOLGA * 2))
    abreviar = len(itens) > 8

    partes = [_abertura(largura, altura, titulo, itens)]

    # Linha de base: sem ela as colunas ficam flutuando no branco.
    partes.append(
        f'<line class="eixo-linha" x1="0" y1="{base}" x2="{largura}" y2="{base}" '
        f'stroke="var(--viz-grade)" stroke-width="1"/>'
    )

    for indice, (rotulo, valor) in enumerate(itens):
        comprimento = _proporcao(valor, maior) * disponivel
        x = indice * passo + (passo - espessura) / 2
        y = base - comprimento
        centro = x + espessura / 2

        partes.append(
            f'<rect class="marca" x="{x:.1f}" y="{y:.1f}" '
            f'width="{espessura:.1f}" height="{comprimento:.1f}" '
            f'rx="{RAIO}" fill="{COR}" data-rotulo="{escape(rotulo)}">'
            f"<title>{escape(rotulo)}: {escape(moeda(valor))}</title>"
            f"</rect>"
        )
        partes.append(
            f'<text class="valor" x="{centro:.1f}" y="{y - 6:.1f}" '
            f'font-size="11" text-anchor="middle">'
            f"{escape(_curto(valor) if abreviar else moeda(valor, simbolo=False))}</text>"
        )
        partes.append(
            f'<text class="eixo" x="{centro:.1f}" y="{altura - 6}" '
            f'font-size="11" text-anchor="middle">{escape(rotulo)}</text>'
        )

    partes.append("</svg>")
    return Markup("".join(partes))


def _curto(valor: Decimal) -> str:
    """`102300` -> `102,3 mil`. So quando ha colunas demais para o valor cheio."""
    numero = float(valor)
    if numero >= 1_000_000:
        return f"{numero / 1_000_000:.1f}".replace(".", ",") + " mi"
    if numero >= 1_000:
        return f"{numero / 1_000:.1f}".replace(".", ",") + " mil"
    return f"{numero:.0f}"


def _abertura(largura: int, altura: float, titulo: str, itens: list) -> str:
    resumo = f"{titulo or 'grafico'} — {len(itens)} itens"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" class="gr" '
        f'viewBox="0 0 {largura} {altura:.0f}" width="100%" height="{altura:.0f}" '
        f'role="img" aria-label="{escape(resumo)}">'
    )


def _sem_dados() -> Markup:
    return Markup('<p class="gr-vazio">Sem dados para o filtro atual.</p>')


def _proporcao(valor: Decimal, maior: Decimal) -> float:
    if maior <= 0:
        return 0.0
    return max(0.0, float(valor) / float(maior))


def _encurtar(rotulo: str) -> str:
    if len(rotulo) <= LIMITE_ROTULO:
        return rotulo
    return rotulo[: LIMITE_ROTULO - 1].rstrip() + "…"


def _dobrar_cauda(itens: list[tuple[str, Decimal]], maximo: int) -> list[tuple[str, Decimal]]:
    """Alem do teto a cauda vira "Outras (n)": mais barras minusculas nao
    resolvem categorias demais."""
    if maximo <= 0 or len(itens) <= maximo:
        return itens
    cabeca, cauda = itens[: maximo - 1], itens[maximo - 1 :]
    soma = sum((valor for _, valor in cauda), Decimal(0))
    return [*cabeca, (f"Outras ({len(cauda)})", soma)]
