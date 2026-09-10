"""Configuracao comum da suite.

De proposito quase vazio: as fixtures de banco e de app vivem em
tests/integration/conftest.py, para que `pytest tests/unit` rode sem Flask,
sem SQLAlchemy e sem banco nenhum de pe. Teste puro que depende de
infraestrutura deixa de ser teste puro.
"""

import sys
from pathlib import Path

# A raiz do projeto no sys.path: a suite roda tanto pelo container quanto
# por um venv solto, e nem sempre o pacote esta instalado.
RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
