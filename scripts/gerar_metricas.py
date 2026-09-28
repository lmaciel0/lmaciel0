"""Gera os cards de estatísticas e linguagens do perfil como SVG.

Roda no GitHub Actions (workflow metricas.yml) com o GITHUB_TOKEN do próprio
workflow, então não depende de serviços externos como o github-readme-stats.
Só conta dados públicos.

Uso: GITHUB_TOKEN=... python scripts/gerar_metricas.py <usuario> <pasta_saida>
     python scripts/gerar_metricas.py --exemplo <pasta_saida>   (dados fictícios)
"""

import json
import os
import sys
import urllib.request
from html import escape
from pathlib import Path

API = "https://api.github.com/graphql"

# Cores do tema tokyonight, o mesmo do card de sequência de contribuições.
FUNDO = "#1a1b27"
TITULO = "#70a5fd"
TEXTO = "#38bdae"
ICONE = "#bf91f3"

LARGURA = 400
ALTURA = 165


def consultar(token: str, query: str, variaveis: dict) -> dict:
    corpo = json.dumps({"query": query, "variables": variaveis}).encode()
    req = urllib.request.Request(API, data=corpo, headers={
        "Authorization": f"bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "gerar-metricas-perfil",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        dados = json.load(resp)
    if dados.get("errors"):
        raise RuntimeError(f"Erro da API do GitHub: {dados['errors']}")
    return dados["data"]


def coletar(token: str, usuario: str) -> dict:
    base = consultar(token, """
        query($login: String!) {
          user(login: $login) {
            contributionsCollection { contributionYears }
            pullRequests { totalCount }
            issues { totalCount }
            repositoriesContributedTo(contributionTypes: [COMMIT, PULL_REQUEST, ISSUE]) { totalCount }
            repositories(first: 100, ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false) {
              nodes {
                stargazerCount
                languages(first: 20, orderBy: {field: SIZE, direction: DESC}) {
                  edges { size node { name color } }
                }
              }
            }
          }
        }""", {"login": usuario})["user"]

    # O total de commits só vem por ano; soma todos os anos com contribuição.
    commits = 0
    for ano in base["contributionsCollection"]["contributionYears"]:
        ano_dados = consultar(token, """
            query($login: String!, $de: DateTime!, $ate: DateTime!) {
              user(login: $login) {
                contributionsCollection(from: $de, to: $ate) { totalCommitContributions }
              }
            }""", {"login": usuario, "de": f"{ano}-01-01T00:00:00Z", "ate": f"{ano}-12-31T23:59:59Z"})
        commits += ano_dados["user"]["contributionsCollection"]["totalCommitContributions"]

    linguagens: dict[str, dict] = {}
    estrelas = 0
    for repo in base["repositories"]["nodes"]:
        estrelas += repo["stargazerCount"]
        for aresta in repo["languages"]["edges"]:
            nome = aresta["node"]["name"]
            item = linguagens.setdefault(nome, {"bytes": 0, "cor": aresta["node"]["color"] or "#858585"})
            item["bytes"] += aresta["size"]

    return {
        "estrelas": estrelas,
        "commits": commits,
        "prs": base["pullRequests"]["totalCount"],
        "issues": base["issues"]["totalCount"],
        "contribuiu": base["repositoriesContributedTo"]["totalCount"],
        "linguagens": linguagens,
    }


def _svg(titulo: str, conteudo: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{LARGURA}" height="{ALTURA}" viewBox="0 0 {LARGURA} {ALTURA}" role="img" aria-label="{escape(titulo)}">
  <style>
    .titulo {{ font: 600 18px 'Segoe UI', Ubuntu, sans-serif; fill: {TITULO}; }}
    .rotulo {{ font: 600 14px 'Segoe UI', Ubuntu, sans-serif; fill: {TEXTO}; }}
    .valor {{ font: 700 14px 'Segoe UI', Ubuntu, sans-serif; fill: {TEXTO}; }}
    .lang {{ font: 400 12px 'Segoe UI', Ubuntu, sans-serif; fill: {TEXTO}; }}
  </style>
  <rect width="{LARGURA}" height="{ALTURA}" rx="4.5" fill="{FUNDO}"/>
  <text x="25" y="35" class="titulo">{escape(titulo)}</text>
{conteudo}
</svg>
"""


def card_estatisticas(dados: dict) -> str:
    linhas = [
        ("Total de estrelas", dados["estrelas"]),
        ("Total de commits", dados["commits"]),
        ("Total de PRs", dados["prs"]),
        ("Total de issues", dados["issues"]),
        ("Contribuiu em (repos)", dados["contribuiu"]),
    ]
    partes = []
    for i, (rotulo, valor) in enumerate(linhas):
        y = 62 + i * 21
        partes.append(
            f'  <circle cx="31" cy="{y - 5}" r="4" fill="{ICONE}"/>\n'
            f'  <text x="45" y="{y}" class="rotulo">{escape(rotulo)}:</text>\n'
            f'  <text x="250" y="{y}" class="valor">{valor}</text>'
        )
    return _svg("Estatísticas do GitHub", "\n".join(partes))


def card_linguagens(linguagens: dict, maximo: int = 6) -> str:
    total = sum(item["bytes"] for item in linguagens.values()) or 1
    top = sorted(linguagens.items(), key=lambda par: par[1]["bytes"], reverse=True)[:maximo]
    soma_top = sum(item["bytes"] for _, item in top) or 1

    # Barra única dividida proporcionalmente entre as linguagens exibidas.
    barra, x = [], 25.0
    largura_barra = LARGURA - 50
    for nome, item in top:
        w = largura_barra * item["bytes"] / soma_top
        barra.append(f'    <rect x="{x:.2f}" y="50" width="{w:.2f}" height="8" fill="{item["cor"]}"/>')
        x += w
    partes = [
        '  <clipPath id="barra"><rect x="25" y="50" width="350" height="8" rx="4"/></clipPath>',
        '  <g clip-path="url(#barra)">',
        *barra,
        "  </g>",
    ]
    for i, (nome, item) in enumerate(top):
        coluna, linha = i % 2, i // 2
        cx, y = 30 + coluna * 180, 85 + linha * 25
        pct = 100 * item["bytes"] / total
        partes.append(
            f'  <circle cx="{cx}" cy="{y - 4}" r="5" fill="{item["cor"]}"/>\n'
            f'  <text x="{cx + 12}" y="{y}" class="lang">{escape(nome)} {pct:.1f}%</text>'
        )
    return _svg("Linguagens mais usadas", "\n".join(partes))


EXEMPLO = {
    "estrelas": 3, "commits": 142, "prs": 13, "issues": 1, "contribuiu": 3,
    "linguagens": {
        "Java": {"bytes": 60000, "cor": "#b07219"},
        "Python": {"bytes": 90000, "cor": "#3572A5"},
        "TypeScript": {"bytes": 30000, "cor": "#3178c6"},
        "CSS": {"bytes": 8000, "cor": "#663399"},
        "Batchfile": {"bytes": 4000, "cor": "#C1F12E"},
        "Shell": {"bytes": 1500, "cor": "#89e051"},
        "HTML": {"bytes": 700, "cor": "#e34c26"},
    },
}


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    usuario, saida = sys.argv[1], Path(sys.argv[2])
    if usuario == "--exemplo":
        dados = EXEMPLO
    else:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            sys.exit("Defina a variável de ambiente GITHUB_TOKEN.")
        dados = coletar(token, usuario)
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "estatisticas.svg").write_text(card_estatisticas(dados), encoding="utf-8")
    (saida / "linguagens.svg").write_text(card_linguagens(dados["linguagens"]), encoding="utf-8")
    print(f"Cards gerados em {saida}/")


if __name__ == "__main__":
    main()
