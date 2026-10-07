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

  // <select data-enviar-ao-mudar> dentro de um form GET.
  document.addEventListener('change', function (evento) {
    var campo = evento.target.closest('[data-enviar-ao-mudar]');
    if (!campo) return;
    var formulario = campo.closest('form');
    if (!formulario) return;
    // Trocar o mês descarta o dia: 31 não existe em fevereiro.
    if (campo.name === 'mes') {
      var dia = formulario.querySelector('[name="dia"]');
      if (dia) dia.value = '';
    }
    formulario.submit();
  });

  // --- múltipla escolha: cada chip carrega um hidden com o nome do campo ---

  function chipDoValor(campo, valor) {
    var chip = document.createElement('span');
    chip.className = 'chip-escolhido';

    var texto = document.createElement('span');
    texto.textContent = valor;
    chip.appendChild(texto);

    var oculto = document.createElement('input');
    oculto.type = 'hidden';
    oculto.name = campo;
    oculto.value = valor;
    chip.appendChild(oculto);

    var tirar = document.createElement('button');
    tirar.type = 'button';
    tirar.className = 'tirar-escolhido';
    tirar.setAttribute('data-tirar-escolhido', '');
    tirar.setAttribute('aria-label', 'Tirar ' + valor);
    tirar.textContent = '×';
    chip.appendChild(tirar);

    return chip;
  }

  function adicionar(caixa, valor) {
    valor = (valor || '').trim();
    if (!valor) return false;

    var campo = caixa.getAttribute('data-multi');
    var escolhidos = caixa.querySelector('[data-escolhidos]');
    var jaTem = Array.prototype.some.call(
      escolhidos.querySelectorAll('input[type=hidden]'),
      function (oculto) { return oculto.value === valor; }
    );
    if (jaTem) return false;

    escolhidos.appendChild(chipDoValor(campo, valor));
    return true;
  }

  document.addEventListener('change', function (evento) {
    var entrada = evento.target.closest('[data-adicionar]');
    if (!entrada) return;
    var caixa = entrada.closest('[data-multi]');
    if (!caixa) return;
    if (adicionar(caixa, entrada.value)) entrada.value = '';
  });

  // Enter adiciona, em vez de enviar o formulário meio preenchido.
  document.addEventListener('keydown', function (evento) {
    if (evento.key !== 'Enter') return;
    var entrada = evento.target.closest('[data-adicionar]');
    if (!entrada || !entrada.value.trim()) return;
    var caixa = entrada.closest('[data-multi]');
    if (!caixa) return;
    evento.preventDefault();
    if (adicionar(caixa, entrada.value)) entrada.value = '';
  });

  document.addEventListener('click', function (evento) {
    var tirar = evento.target.closest('[data-tirar-escolhido]');
    if (!tirar) return;
    evento.preventDefault();
    tirar.closest('.chip-escolhido').remove();
  });

  // --- seleção que atravessa as páginas ------------------------------------
  // O marcado na página 1 não está no DOM da 10: os ids ficam no sessionStorage.

  var CHAVE = 'despesas-selecionadas';
  // Situação (div, aceita, ok) e valor de cada marcada: a linha de outra página
  // não está no DOM, e a barra precisa dizer quantas mudam e quanto somam.
  var CHAVE_ESTADO = 'despesas-selecionadas-estado';
  var moeda = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });

  function registro(caixa) {
    return {
      e: caixa.getAttribute('data-estado') || 'ok',
      v: parseFloat(caixa.getAttribute('data-valor')) || 0,
    };
  }

  function estados() {
    try {
      return JSON.parse(window.sessionStorage.getItem(CHAVE_ESTADO)) || {};
    } catch (erro) {
      return {};
    }
  }

  function guardarEstados(mapa) {
    try {
      window.sessionStorage.setItem(CHAVE_ESTADO, JSON.stringify(mapa));
    } catch (erro) {
      /* storage bloqueado */
    }
  }

  function lidas() {
    try {
      return JSON.parse(window.sessionStorage.getItem(CHAVE)) || [];
    } catch (erro) {
      return [];
    }
  }

  function guardar(ids) {
    try {
      window.sessionStorage.setItem(CHAVE, JSON.stringify(ids));
    } catch (erro) {
      /* storage bloqueado: a seleção vale só nesta página */
    }
  }

  function barra() {
    return document.querySelector('[data-barra-selecao]');
  }

  function pintar() {
    var ids = lidas();
    var faixa = barra();
    if (!faixa) return;

    var contador = faixa.querySelector('[data-contagem]');
    if (contador) contador.textContent = ids.length;
    faixa.hidden = ids.length === 0;

    var mapa = estados();
    Array.prototype.forEach.call(faixa.querySelectorAll('[data-acao-lote]'), function (botao) {
      var alvo = botao.getAttribute('data-acao-lote');
      var quantas = ids.filter(function (id) { return mapa[id] && mapa[id].e === alvo; }).length;
      botao.querySelector('[data-quantas]').textContent = '(' + quantas + ')';
      botao.disabled = quantas === 0;
    });

    var total = ids.reduce(function (soma, id) { return soma + (mapa[id] ? mapa[id].v : 0); }, 0);
    var valor = faixa.querySelector('[data-valor-selecao]');
    if (valor) valor.textContent = moeda.format(total);
    faixa.setAttribute('data-resumo', ids.length + ' lançamento(s), ' + moeda.format(total));

    var nesta = faixa.querySelector('[data-nesta-pagina]');
    if (nesta) {
      var visiveis = document.querySelectorAll('[data-selecionavel]').length;
      var marcadasAqui = document.querySelectorAll('[data-selecionavel]:checked').length;
      nesta.textContent = ids.length > marcadasAqui
        ? ' (' + marcadasAqui + ' nesta página de ' + visiveis + ')'
        : '';
    }
  }

  function restaurar() {
    var ids = lidas();
    var mapa = estados();
    Array.prototype.forEach.call(
      document.querySelectorAll('[data-selecionavel]'),
      function (caixa) {
        caixa.checked = ids.indexOf(caixa.value) !== -1;
        if (caixa.checked) mapa[caixa.value] = registro(caixa);
      }
    );
    guardarEstados(mapa);
    pintar();
  }

  document.addEventListener('change', function (evento) {
    var caixa = evento.target.closest('[data-selecionavel]');
    if (caixa) {
      var ids = lidas();
      var mapa = estados();
      var posicao = ids.indexOf(caixa.value);
      if (caixa.checked && posicao === -1) ids.push(caixa.value);
      if (!caixa.checked && posicao !== -1) ids.splice(posicao, 1);
      if (caixa.checked) mapa[caixa.value] = registro(caixa);
      else delete mapa[caixa.value];
      guardar(ids);
      guardarEstados(mapa);
      pintar();
      return;
    }

    var todos = evento.target.closest('[data-marcar-todos]');
    if (todos) {
      Array.prototype.forEach.call(
        document.querySelectorAll('[data-selecionavel]'),
        function (item) {
          item.checked = todos.checked;
          item.dispatchEvent(new Event('change', { bubbles: true }));
        }
      );
    }
  });

  document.addEventListener('click', function (evento) {
    if (!evento.target.closest('[data-limpar-selecao]')) return;
    evento.preventDefault();
    guardar([]);
    guardarEstados({});
    restaurar();
  });

  // Exportar a seleção: a mesma janela de exportação, com os ids na URL.
  document.addEventListener('click', function (evento) {
    var botao = evento.target.closest('[data-exportar-selecao]');
    if (!botao) return;
    var ids = lidas();
    if (!ids.length) return;
    var faixa = barra();
    var link = document.createElement('a');
    link.href = botao.getAttribute('data-url') + '?' + ids.map(function (id) {
      return 'id=' + encodeURIComponent(id);
    }).join('&');
    link.setAttribute('data-exportar', 'Excel');
    link.setAttribute('data-filtro', ids.length + ' lançamento(s) selecionado(s)');
    link.setAttribute('data-linhas', faixa ? faixa.getAttribute('data-resumo') : '');
    link.hidden = true;
    document.body.appendChild(link);
    link.click();
    link.remove();
  });

  // Sem isto o lote agiria só sobre o que está visível.
  document.addEventListener('submit', function (evento) {
    var formulario = evento.target.closest('[data-forma-lote]');
    if (!formulario) return;

    var botao = evento.submitter;
    if (botao && botao.hasAttribute('data-excluir-lote')) {
      var faixa = barra();
      var resumo = faixa ? faixa.getAttribute('data-resumo') : '';
      if (!window.confirm('Excluir ' + resumo + '? A exclusão fica registrada na auditoria.')) {
        evento.preventDefault();
        return;
      }
    }

    Array.prototype.forEach.call(
      formulario.querySelectorAll('[data-id-de-outra-pagina]'),
      function (velho) { velho.remove(); }
    );

    var visiveis = {};
    Array.prototype.forEach.call(
      document.querySelectorAll('[data-selecionavel]'),
      function (caixa) { visiveis[caixa.value] = true; }
    );

    lidas().forEach(function (id) {
      if (visiveis[id]) return;
      var oculto = document.createElement('input');
      oculto.type = 'hidden';
      oculto.name = 'ids';
      oculto.value = id;
      oculto.setAttribute('data-id-de-outra-pagina', '');
      formulario.appendChild(oculto);
    });

    guardar([]);
    guardarEstados({});
  });

  document.addEventListener('DOMContentLoaded', restaurar);
  document.body.addEventListener('htmx:afterSwap', restaurar);
})();

// Importação: a planilha pode ser arrastada para a área do arquivo.
(function () {
  'use strict';

  function nome(area, input) {
    var alvo = area.querySelector('[data-nome-arquivo]');
    if (alvo) alvo.textContent = input.files.length ? input.files[0].name : 'Nenhum arquivo escolhido';
  }

  document.addEventListener('DOMContentLoaded', function () {
    Array.prototype.forEach.call(document.querySelectorAll('[data-area-arquivo]'), function (area) {
      var input = area.querySelector('input[type=file]');
      input.addEventListener('change', function () { nome(area, input); });
      ['dragenter', 'dragover'].forEach(function (tipo) {
        area.addEventListener(tipo, function (evento) {
          evento.preventDefault();
          area.classList.add('sobre');
        });
      });
      ['dragleave', 'drop'].forEach(function (tipo) {
        area.addEventListener(tipo, function (evento) {
          evento.preventDefault();
          area.classList.remove('sobre');
        });
      });
      area.addEventListener('drop', function (evento) {
        if (!evento.dataTransfer.files.length) return;
        input.files = evento.dataTransfer.files;
        nome(area, input);
      });
    });
  });
})();
