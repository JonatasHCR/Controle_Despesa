/*
 * Filtros que se aplicam sozinhos, e os três campos múltiplos como lista com
 * busca. A lista nasce do <datalist> que o servidor já manda; sem JS, ele fica.
 */
(function () {
  'use strict';

  var LIMITE = 300;

  function semAcento(texto) {
    return String(texto).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  }

  function enviar(formulario) {
    if (formulario.requestSubmit) formulario.requestSubmit();
    else formulario.submit();
  }

  function elemento(tag, classe, texto) {
    var el = document.createElement(tag);
    if (classe) el.className = classe;
    if (texto != null) el.textContent = texto;
    return el;
  }

  // --- campo múltiplo ------------------------------------------------------

  function montarMulti(caixa) {
    var formulario = caixa.closest('form');
    var campo = caixa.getAttribute('data-multi');
    var todos = caixa.getAttribute('data-todos') || 'Todos';
    var datalist = caixa.querySelector('datalist');
    var escolhidos = caixa.querySelector('[data-escolhidos]');
    var digitavel = caixa.querySelector('[data-adicionar]');
    if (!datalist || !escolhidos || !digitavel) return;

    var opcoes = Array.prototype.map.call(datalist.options, function (o) { return o.value; });
    var marcados = Array.prototype.map.call(
      escolhidos.querySelectorAll('input[type=hidden]'), function (i) { return i.value; });
    var original = marcados.slice().sort().join('\n');

    escolhidos.hidden = true;
    digitavel.hidden = true;

    var botao = elemento('button', 'multi-botao');
    botao.type = 'button';
    botao.id = campo + '-multi';
    botao.setAttribute('aria-haspopup', 'listbox');
    botao.setAttribute('aria-expanded', 'false');
    var valor = elemento('span', 'multi-valor');
    var contador = elemento('span', 'multi-contador');
    botao.appendChild(valor);
    botao.appendChild(contador);
    var rotulo = caixa.querySelector('label');
    if (rotulo) rotulo.htmlFor = botao.id;

    var painel = elemento('div', 'multi-painel');
    painel.hidden = true;
    var busca = elemento('input', 'multi-busca');
    busca.type = 'search';
    busca.placeholder = 'Buscar…';
    busca.setAttribute('aria-label', 'Buscar ' + (rotulo ? rotulo.textContent.trim().toLowerCase() : ''));
    var barra = elemento('div', 'multi-acoes');
    var marcarVisiveis = elemento('button', 'botao-fantasma', 'Marcar visíveis');
    var limpar = elemento('button', 'botao-fantasma', 'Limpar');
    marcarVisiveis.type = limpar.type = 'button';
    var quantos = elemento('span', 'multi-quantos');
    barra.appendChild(marcarVisiveis);
    barra.appendChild(limpar);
    barra.appendChild(quantos);
    var lista = elemento('ul', 'multi-lista');
    lista.setAttribute('role', 'listbox');
    lista.setAttribute('aria-multiselectable', 'true');
    var rodape = elemento('div', 'multi-rodape');
    var aplicar = elemento('button', 'botao botao-mini botao-principal', 'Aplicar');
    aplicar.type = 'button';
    rodape.appendChild(aplicar);

    painel.appendChild(busca);
    painel.appendChild(barra);
    painel.appendChild(lista);
    painel.appendChild(rodape);
    caixa.appendChild(botao);
    caixa.appendChild(painel);

    var visiveis = [];

    function pintarBotao() {
      contador.hidden = marcados.length < 2;
      contador.textContent = marcados.length;
      valor.classList.toggle('sem-escolha', !marcados.length);
      valor.textContent = !marcados.length ? todos
        : marcados.length === 1 ? marcados[0] : marcados.length + ' selecionados';
      botao.title = marcados.join('\n');
    }

    function comDestaque(texto, termo) {
      var li = document.createDocumentFragment();
      var posicao = termo ? semAcento(texto).indexOf(termo) : -1;
      if (posicao < 0) {
        li.appendChild(document.createTextNode(texto));
        return li;
      }
      li.appendChild(document.createTextNode(texto.slice(0, posicao)));
      li.appendChild(elemento('mark', '', texto.slice(posicao, posicao + termo.length)));
      li.appendChild(document.createTextNode(texto.slice(posicao + termo.length)));
      return li;
    }

    function pintarLista() {
      var termo = semAcento(busca.value.trim());
      visiveis = termo ? opcoes.filter(function (o) { return semAcento(o).indexOf(termo) >= 0; }) : opcoes;
      lista.textContent = '';
      visiveis.slice(0, LIMITE).forEach(function (opcao) {
        var item = elemento('li');
        var etiqueta = elemento('label');
        var caixinha = elemento('input');
        caixinha.type = 'checkbox';
        caixinha.value = opcao;
        caixinha.checked = marcados.indexOf(opcao) >= 0;
        var texto = elemento('span', 'multi-texto');
        texto.title = opcao;
        texto.appendChild(comDestaque(opcao, termo));
        etiqueta.appendChild(caixinha);
        etiqueta.appendChild(texto);
        item.appendChild(etiqueta);
        lista.appendChild(item);
      });
      if (!visiveis.length) {
        lista.appendChild(elemento('li', 'multi-vazio', 'Nada encontrado para “' + busca.value + '”.'));
      } else if (visiveis.length > LIMITE) {
        lista.appendChild(elemento('li', 'multi-vazio',
          'Mostrando ' + LIMITE + ' de ' + visiveis.length + '. Digite para refinar.'));
      }
      quantos.textContent = marcados.length + ' de ' + opcoes.length;
    }

    function alternar(opcao, ligado) {
      var posicao = marcados.indexOf(opcao);
      if (ligado && posicao < 0) marcados.push(opcao);
      if (!ligado && posicao >= 0) marcados.splice(posicao, 1);
    }

    function abrir() {
      fecharOutros(caixa);
      painel.hidden = false;
      caixa.classList.add('aberto');
      botao.setAttribute('aria-expanded', 'true');
      painel.classList.toggle('a-direita', caixa.getBoundingClientRect().left + 340 > window.innerWidth);
      pintarLista();
      busca.focus();
    }

    // Aplicar só ao fechar: marcar três itens não pode recarregar a tela três vezes.
    function fechar() {
      if (painel.hidden) return;
      painel.hidden = true;
      caixa.classList.remove('aberto');
      botao.setAttribute('aria-expanded', 'false');
      if (marcados.slice().sort().join('\n') === original) return;

      escolhidos.textContent = '';
      marcados.forEach(function (opcao) {
        var oculto = elemento('input');
        oculto.type = 'hidden';
        oculto.name = campo;
        oculto.value = opcao;
        escolhidos.appendChild(oculto);
      });
      original = marcados.slice().sort().join('\n');
      // Fora da barra de filtros (ex.: limpeza na administração) só guarda a escolha.
      if (formulario.hasAttribute('data-filtros')) enviar(formulario);
    }

    caixa._fechar = fechar;

    botao.addEventListener('click', function () { painel.hidden ? abrir() : fechar(); });
    busca.addEventListener('input', pintarLista);
    busca.addEventListener('keydown', function (evento) {
      if (evento.key === 'Enter') {
        evento.preventDefault();
        if (visiveis.length === 1) {
          alternar(visiveis[0], marcados.indexOf(visiveis[0]) < 0);
          pintarLista();
          pintarBotao();
        }
      }
      if (evento.key === 'Escape') {
        fechar();
        botao.focus();
      }
    });
    lista.addEventListener('change', function (evento) {
      alternar(evento.target.value, evento.target.checked);
      quantos.textContent = marcados.length + ' de ' + opcoes.length;
      pintarBotao();
    });
    marcarVisiveis.addEventListener('click', function () {
      visiveis.slice(0, LIMITE).forEach(function (opcao) { alternar(opcao, true); });
      pintarLista();
      pintarBotao();
    });
    limpar.addEventListener('click', function () {
      marcados = [];
      pintarLista();
      pintarBotao();
    });
    aplicar.addEventListener('click', fechar);

    pintarBotao();
  }

  function fecharOutros(exceto) {
    Array.prototype.forEach.call(document.querySelectorAll('[data-multi].aberto'), function (caixa) {
      if (caixa !== exceto && caixa._fechar) caixa._fechar();
    });
  }

  document.addEventListener('click', function (evento) {
    if (!evento.target.closest('[data-multi]')) fecharOutros(null);
  });

  // --- o resto do formulário -------------------------------------------------

  function montarFiltros(formulario) {
    Array.prototype.forEach.call(formulario.querySelectorAll('[data-multi]'), montarMulti);

    var inicio = formulario.querySelector('[name=inicio]');
    var fim = formulario.querySelector('[name=fim]');

    formulario.addEventListener('change', function (evento) {
      var alvo = evento.target;
      if (alvo.closest('.multi-painel') || alvo.hasAttribute('data-adicionar')) return;

      // A inicial não passa da final, e a final não fica antes da inicial.
      if (alvo === inicio && fim) {
        fim.min = inicio.value;
        if (fim.value && inicio.value > fim.value) fim.value = inicio.value;
      }
      if (alvo === fim && inicio) {
        inicio.max = fim.value;
        if (inicio.value && fim.value < inicio.value) inicio.value = fim.value;
      }
      enviar(formulario);
    });

    var alternarMais = formulario.querySelector('[data-alternar-mais]');
    if (alternarMais) {
      alternarMais.addEventListener('click', function () {
        var alvo = document.getElementById(alternarMais.getAttribute('aria-controls'));
        var aberto = alvo.classList.toggle('aberta');
        alternarMais.setAttribute('aria-expanded', aberto ? 'true' : 'false');
        alternarMais.textContent = aberto ? 'Menos filtros' : 'Mais filtros';
      });
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    Array.prototype.forEach.call(document.querySelectorAll('[data-filtros]'), montarFiltros);
    Array.prototype.forEach.call(document.querySelectorAll('[data-multi]'), function (caixa) {
      if (!caixa.closest('[data-filtros]')) montarMulti(caixa);
    });

    // Limpeza: os filtros só valem para despesas.
    var alvo = document.querySelector('[data-alvo-limpeza]');
    if (alvo) {
      var alternar = function () {
        Array.prototype.forEach.call(document.querySelectorAll('[data-so-despesas]'), function (bloco) {
          bloco.hidden = alvo.value !== 'despesas';
        });
      };
      alvo.addEventListener('change', alternar);
      alternar();
    }
  });
})();
