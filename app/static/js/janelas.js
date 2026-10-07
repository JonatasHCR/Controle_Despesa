/*
 * Gaveta do lançamento, janela de exportação e grupos do relatório.
 */
(function () {
  'use strict';

  function elemento(tag, classe, texto) {
    var el = document.createElement(tag);
    if (classe) el.className = classe;
    if (texto != null) el.textContent = texto;
    return el;
  }

  function dialogo(classe) {
    var janela = elemento('dialog', classe);
    document.body.appendChild(janela);
    janela.addEventListener('close', function () { janela.remove(); });
    // Clique no fundo escurecido fecha.
    janela.addEventListener('click', function (evento) {
      if (evento.target === janela) janela.close();
    });
    return janela;
  }

  // --- gaveta: clique na linha abre o lançamento ---------------------------

  document.addEventListener('click', function (evento) {
    var linha = evento.target.closest('tr[data-detalhe]');
    if (!linha || evento.target.closest('a, button, input, label, form')) return;

    var gaveta = dialogo('gaveta');
    gaveta.appendChild(elemento('p', 'gaveta-carregando', 'Carregando…'));
    gaveta.showModal();

    fetch(linha.getAttribute('data-detalhe'), { credentials: 'same-origin' })
      .then(function (resposta) {
        if (!resposta.ok) throw new Error();
        return resposta.text();
      })
      .then(function (html) { gaveta.innerHTML = html; })
      .catch(function () {
        gaveta.textContent = '';
        gaveta.appendChild(elemento('p', 'gaveta-carregando',
          'Não deu para abrir o lançamento. Recarregue a página e tente de novo.'));
      });
  });

  document.addEventListener('click', function (evento) {
    if (!evento.target.closest('[data-fechar-gaveta]')) return;
    var gaveta = evento.target.closest('dialog');
    if (gaveta) gaveta.close();
  });

  // --- exportação: o servidor gera, a janela mostra o andamento ------------

  function nomeDoArquivo(resposta, padrao) {
    var cabecalho = resposta.headers.get('Content-Disposition') || '';
    var achado = /filename="?([^";]+)"?/.exec(cabecalho);
    return achado ? achado[1] : padrao;
  }

  function tamanho(bytes) {
    if (bytes >= 1048576) return (bytes / 1048576).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + ' MB';
    return Math.max(1, Math.round(bytes / 1024)) + ' KB';
  }

  document.addEventListener('click', function (evento) {
    var link = evento.target.closest('a[data-exportar]');
    if (!link || evento.ctrlKey || evento.metaKey || evento.shiftKey) return;
    evento.preventDefault();

    var tipo = link.getAttribute('data-exportar');
    var janela = dialogo('janela-exportar');

    var topo = elemento('header', 'janela-topo');
    topo.appendChild(elemento('h2', '', 'Gerar ' + tipo));
    var fechar = elemento('button', 'botao-icone', '✕');
    fechar.type = 'button';
    fechar.setAttribute('aria-label', 'Fechar');
    fechar.addEventListener('click', function () { janela.close(); });
    topo.appendChild(fechar);

    var corpo = elemento('div', 'janela-corpo');
    var ficha = elemento('dl', 'ficha');
    [['Filtro', link.getAttribute('data-filtro') || legendaDaPagina()],
     ['Conteúdo', link.getAttribute('data-linhas')],
     ['Total', link.getAttribute('data-total')]].forEach(function (par) {
      if (!par[1]) return;
      ficha.appendChild(elemento('dt', '', par[0]));
      ficha.appendChild(elemento('dd', '', par[1]));
    });
    corpo.appendChild(ficha);

    var passos = elemento('ol', 'passos');
    var nomes = ['Pedindo ao servidor', 'Gerando o ' + tipo, 'Baixando o arquivo'];
    var itens = nomes.map(function (nome) {
      var item = elemento('li', '', nome);
      passos.appendChild(item);
      return item;
    });
    corpo.appendChild(passos);
    var aviso = elemento('p', 'janela-aviso');
    aviso.hidden = true;
    corpo.appendChild(aviso);

    var pe = elemento('footer', 'janela-pe');
    var fecharPe = elemento('button', 'botao', 'Fechar');
    fecharPe.type = 'button';
    fecharPe.addEventListener('click', function () { janela.close(); });
    pe.appendChild(fecharPe);

    janela.appendChild(topo);
    janela.appendChild(corpo);
    janela.appendChild(pe);
    janela.showModal();

    function etapa(n) {
      itens.forEach(function (item, i) {
        item.className = i < n ? 'feito' : i === n ? 'andando' : '';
      });
    }

    function falhou(mensagem) {
      itens.forEach(function (item) { if (item.className === 'andando') item.className = 'falhou'; });
      aviso.hidden = false;
      aviso.className = 'janela-aviso erro';
      aviso.textContent = mensagem;
    }

    etapa(0);
    var gerando = setTimeout(function () { etapa(1); }, 300);

    fetch(link.href, { credentials: 'same-origin', headers: { 'X-Exportar': '1' } })
      .then(function (resposta) {
        clearTimeout(gerando);
        if (resposta.status === 422) {
          return resposta.json().then(function (corpo) { throw new Error(corpo.erro); });
        }
        if (resposta.status === 429) {
          throw new Error('Muitos arquivos gerados em pouco tempo. Espere um minuto e tente de novo.');
        }
        var conteudo = resposta.headers.get('Content-Type') || '';
        if (!resposta.ok || conteudo.indexOf('text/html') === 0) {
          throw new Error('O servidor não devolveu o arquivo. Recarregue a página e tente de novo.');
        }
        etapa(2);
        var nome = nomeDoArquivo(resposta, 'controle-despesa.' + (tipo === 'PDF' ? 'pdf' : 'xlsx'));
        return resposta.blob().then(function (arquivo) { return { arquivo: arquivo, nome: nome }; });
      })
      .then(function (pronto) {
        var endereco = URL.createObjectURL(pronto.arquivo);
        var baixar = elemento('a');
        baixar.href = endereco;
        baixar.download = pronto.nome;
        document.body.appendChild(baixar);
        baixar.click();
        baixar.remove();
        setTimeout(function () { URL.revokeObjectURL(endereco); }, 60000);

        etapa(3);
        aviso.hidden = false;
        aviso.className = 'janela-aviso pronto';
        aviso.textContent = '';
        aviso.appendChild(elemento('strong', 'num', pronto.nome));
        aviso.appendChild(document.createTextNode(' · ' + tamanho(pronto.arquivo.size) + '. O download começou.'));
      })
      .catch(function (erro) {
        clearTimeout(gerando);
        falhou(erro.message || 'Não deu para gerar o arquivo.');
      });
  });

  function legendaDaPagina() {
    var chips = document.querySelectorAll('.cabecalho-pagina .chip');
    if (!chips.length) return 'Todos os lançamentos';
    return Array.prototype.map.call(chips, function (chip) {
      return chip.textContent.replace('×', '').replace(/\s+/g, ' ').trim();
    }).join(' · ');
  }

  // --- relatório: abrir e fechar o detalhe de cada grupo -------------------

  function alternarGrupo(linha, abrir) {
    var numero = linha.getAttribute('data-grupo');
    var aberto = abrir == null ? linha.getAttribute('aria-expanded') !== 'true' : abrir;
    linha.setAttribute('aria-expanded', aberto ? 'true' : 'false');
    Array.prototype.forEach.call(
      document.querySelectorAll('tr[data-de-grupo="' + numero + '"]'),
      function (filha) { filha.hidden = !aberto; }
    );
  }

  document.addEventListener('click', function (evento) {
    var linha = evento.target.closest('tr[data-grupo]');
    if (linha) {
      alternarGrupo(linha);
      return;
    }
    var todos = evento.target.closest('[data-abrir-grupos], [data-fechar-grupos]');
    if (!todos) return;
    var abrir = todos.hasAttribute('data-abrir-grupos');
    Array.prototype.forEach.call(document.querySelectorAll('tr[data-grupo]'), function (l) {
      alternarGrupo(l, abrir);
    });
  });

  document.addEventListener('keydown', function (evento) {
    if (evento.key !== 'Enter' && evento.key !== ' ') return;
    var linha = evento.target.closest('tr[data-grupo]');
    if (!linha) return;
    evento.preventDefault();
    alternarGrupo(linha);
  });
})();
