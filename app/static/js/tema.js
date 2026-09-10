/*
 * Tema em tres estados: claro, escuro, ou seguir o sistema.
 *
 * Fica em arquivo, e nao inline, porque a CSP e `script-src 'self'` — sem CDN
 * nessa rede, nao ha motivo para abrir 'unsafe-inline'.
 */
(function () {
  var CHAVE = 'tema';
  var ORDEM = ['sistema', 'claro', 'escuro'];
  var ICONE = { sistema: '◐', claro: '☀', escuro: '☾' };
  var TITULO = {
    sistema: 'Tema: seguindo o sistema',
    claro: 'Tema: claro',
    escuro: 'Tema: escuro',
  };

  function lido() {
    try {
      var valor = localStorage.getItem(CHAVE);
      return ORDEM.indexOf(valor) >= 0 ? valor : 'sistema';
    } catch (e) {
      return 'sistema';
    }
  }

  function aplicar(tema) {
    if (tema === 'sistema') {
      document.documentElement.removeAttribute('data-theme');
    } else {
      document.documentElement.setAttribute('data-theme', tema === 'escuro' ? 'dark' : 'light');
    }
    var botao = document.getElementById('alternar-tema');
    if (botao) {
      botao.textContent = ICONE[tema];
      botao.title = TITULO[tema];
      botao.setAttribute('aria-label', TITULO[tema]);
    }
  }

  aplicar(lido());

  document.addEventListener('DOMContentLoaded', function () {
    aplicar(lido());
    var botao = document.getElementById('alternar-tema');
    if (!botao) return;
    botao.addEventListener('click', function () {
      var proximo = ORDEM[(ORDEM.indexOf(lido()) + 1) % ORDEM.length];
      try {
        localStorage.setItem(CHAVE, proximo);
      } catch (e) {
        /* navegador com storage bloqueado: o tema vale so nesta pagina */
      }
      aplicar(proximo);
    });
  });
})();
