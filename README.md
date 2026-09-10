# Controle de Despesa

Gestão de despesas por centro de custo: importa a planilha do ERP, guarda os
lançamentos, permite pesquisar por qualquer campo e gera relatório em PDF ou
Excel com os totais calculados na hora.

É o quinto sistema da plataforma UFC Engenharia, e segue a mesma pegada dos
outros: login unificado no Keycloak, painel administrativo, auditoria e backup
automático.

| | |
|---|---|
| Porta | **3050** |
| Grupo no Keycloak | `/apps/controle-despesa` |
| Client | `controle-despesa-web` |
| Projeto Compose | `controle_despesa` |

## Subir

```bash
cp .env.exemplo .env      # e preencha; o infra/scripts/sync_host_ip.py cuida do resto
docker compose up -d --build
```

O `stack.ps1` da raiz sobe os cinco na ordem certa (o Keycloak precisa estar
saudável antes das aplicações).

## Rodar a suíte

```bash
docker compose up -d db-test
docker compose run --rm --no-deps -e APP_CONFIG=test web pytest
docker compose run --rm --no-deps -e APP_CONFIG=test web pytest --cov=app --cov-report=term-missing
docker compose run --rm --no-deps web ruff check .
```

Os testes rodam contra um PostgreSQL de verdade (`db-test`), e não SQLite: a
busca por campo e os agrupamentos dependem de `ILIKE`, `date_trunc` e
`IS DISTINCT FROM` se comportando como em produção.

`pytest tests/unit` roda sem Flask, sem banco e sem container — por isso
`app/__init__.py` não importa Flask.

## Como o sistema está organizado

```
app/
  factory.py         create_app: extensões, blueprints, filtros, erros
  config.py          Dev / Test / Prod
  models/            despesa, dominio, usuario, importacao, auditoria
  importacao/        planilha.py (parser puro) + servico.py + rotas
  despesas/          filtros.py (o motor de consulta) + consulta.py + rotas
  relatorios/        excel.py (XlsxWriter), pdf.py (WeasyPrint), rotas
  graficos/svg.py    barras e colunas, SVG gerado no servidor
  auth/              oidc.py, guardas.py, rotas
  admin/             manutencao.py (backup/restauração/limpeza) + rotas
  auditoria/         servico.registrar() + leitura
```

### O que vale saber antes de mexer

**A planilha do ERP tem 39 linhas de subtotal intercaladas.** Nenhuma vira
registro. Todo total do sistema é `SUM()` em SQL sobre o filtro corrente — é o
que permite o relatório ter os totais do recorte pedido, e não os que o Excel
congelou na origem.

**Os valores vêm negativos e são gravados positivos** (`abs()` na importação).
Tudo aqui é despesa; o sinal só atrapalharia somas e gráficos.

**Divergência é derivada, nunca armazenada.** `Despesa.divergente` e
`Despesa.diferenca` são `hybrid_property`: a mesma definição serve o template
Jinja e o `WHERE` do SQL. Guardar a flag obrigaria a recalcular em todo
`UPDATE`. A expressão usa `IS DISTINCT FROM`, e não `<>`, porque com `NULL` de
um lado o `<>` devolve `NULL` e a linha sumiria do filtro em silêncio.

**A importação é idempotente por `referencia`.** Reimportar o mesmo arquivo
atualiza em vez de duplicar, e o `sha256` em `tb_importacoes` avisa que aquele
arquivo já entrou. Como a planilha é a fonte, reimportar sobrescreve edições
feitas à mão.

**Quem entra é decidido pelo Keycloak** (grupo `/apps/controle-despesa`); **o
que a pessoa faz é decidido pelo perfil local** (`leitor` / `operador` /
`admin`). Perder o grupo desativa o usuário, nunca o apaga — despesas e
auditoria apontam para ele.

**A auditoria não é middleware.** Cada serviço chama `registrar()` e o commit
fica com quem chamou, para que um rollback derrube o registro junto com a
operação que falhou.

**Sem CDN.** A rede é LAN com IP fixo e sem TLS, então HTMX e CSS são
vendorizados e a CSP fica em `default-src 'self'` — inclusive `style-src`, e é
por isso que os templates não usam `style=` inline.

**Migrações têm autogenerate ligado** (`flask db migrate`), ao contrário do
radar. O `migrations/env.py` filtra `tb_sessoes`, que o Flask-Session cria em
runtime e o Alembic tentaria dropar.

## Design

Paleta herdada do portal: vermelho UFC Engenharia só na marca, resto neutro,
tema em três estados (claro, escuro, seguir o sistema).

Os gráficos usam **uma cor só** — são série única comparando magnitude, e
colorir por categoria faria a cor mudar de dono a cada mudança de ranking. O
vermelho da marca não entra nos dados; o âmbar fica reservado para "divergente",
sempre com ícone e rótulo, nunca cor sozinha. Contrastes conferidos contra as
superfícies reais (5.39:1 no claro, 4.69:1 no escuro).

## Backup

Três produtores, um diretório (`./backups`):

- **sidecar `backup`** — a cada `BACKUP_INTERVAL_HOURS`, `pg_dump --clean
  --if-exists --no-owner --no-privileges`, rotação por `BACKUP_KEEP`;
- **painel administrativo** — `pg_dump -Fc` rodando dentro do container `web`
  (um sidecar precisaria do socket do Docker);
- **`scripts/backup-db.sh`** — manual, a partir do host.

A restauração exige digitar `RESTAURAR`, e um `.sql` sem comandos `DROP` é
recusado: restaurado por cima de um banco povoado, ele aplicaria só os `COPY`
que não conflitam e deixaria o banco misturado.
