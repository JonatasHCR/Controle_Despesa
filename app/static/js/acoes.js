/*
 * Comportamentos declarados por atributo, e não por handler inline.
 *
 * A CSP deste sistema é `script-src 'self'`, e ela bloqueia `onclick=` e
 * companhia — em silêncio. Um `onsubmit="return confirm(...)"` simplesmente não
 * roda, e a exclusão acontece no primeiro clique sem perguntar nada.
 */
(function () {
  'use strict';

  // <form data-confirmar="Excluir a despesa 136914?">
  document.addEventListener('submit', function (evento) {
    var formulario = evento.target.closest('[data-confirmar]');
    if (!formulario) return;
    if (!window.confirm(formulario.getAttribute('data-confirmar'))) {
      evento.preventDefault();
    }
  });

  // <select data-ir-para> — cada <option value> é uma URL.
  document.addEventListener('change', function (evento) {
    var seletor = evento.target.closest('[data-ir-para]');
    if (!seletor || !seletor.value) return;
    window.location.href = seletor.value;
  });
})();
