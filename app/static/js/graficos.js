/*
 * Os dois gráficos do painel em Chart.js. Os dados vêm prontos do servidor no
 * <script id="dados-graficos">; clicar numa barra muda a URL e recarrega.
 */
(function () {
  'use strict';

  var MAX_NATUREZAS = 10;
  var graficos = [];

  function cor(token) {
    return getComputedStyle(document.documentElement).getPropertyValue(token).trim();
  }

  var moeda = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });

  function curto(valor) {
    var abs = Math.abs(valor);
    if (abs >= 1e6) return (valor / 1e6).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + ' mi';
    if (abs >= 1e3) return Math.round(valor / 1e3).toLocaleString('pt-BR') + ' mil';
    return Math.round(valor).toLocaleString('pt-BR');
  }

  function irPara(mudar) {
    var parametros = new URLSearchParams(window.location.search);
    parametros.delete('pagina');
    mudar(parametros);
    window.location.search = parametros.toString();
  }

  // Valor escrito na ponta de cada barra.
  var rotulos = {
    id: 'rotulos',
    afterDatasetsDraw: function (grafico, _args, opcoes) {
      if (!opcoes || !opcoes.ligado) return;
      var ctx = grafico.ctx;
      var deitado = grafico.options.indexAxis === 'y';
      ctx.save();
      ctx.font = '600 10.5px ' + (cor('--mono') || 'monospace');
      ctx.fillStyle = cor('--ink-suave');
      grafico.getDatasetMeta(0).data.forEach(function (barra, i) {
        var valor = grafico.data.datasets[0].data[i];
        if (!valor) return;
        if (deitado) {
          ctx.textAlign = 'left';
          ctx.textBaseline = 'middle';
          ctx.fillText(curto(valor), barra.x + 6, barra.y);
        } else {
          ctx.textAlign = 'center';
          ctx.textBaseline = 'bottom';
          ctx.fillText(curto(valor), barra.x, barra.y - 4);
        }
      });
      ctx.restore();
    },
  };

  function dica(rotulo) {
    return {
      backgroundColor: cor('--ink'),
      titleColor: cor('--ground'),
      bodyColor: cor('--ground'),
      padding: 9,
      cornerRadius: 6,
      displayColors: false,
      callbacks: { label: rotulo },
    };
  }

  function ponteiro(evento, itens) {
    evento.native.target.style.cursor = itens.length ? 'pointer' : 'default';
  }

  function natureza(caixa, dados) {
    var linhas = dados.natureza.slice();
    var total = linhas.reduce(function (s, l) { return s + l.total; }, 0);
    if (linhas.length > MAX_NATUREZAS) {
      var resto = linhas.slice(MAX_NATUREZAS - 1);
      linhas = linhas.slice(0, MAX_NATUREZAS - 1).concat([{
        rotulo: 'Outras ' + resto.length + ' naturezas',
        total: resto.reduce(function (s, l) { return s + l.total; }, 0),
        quantidade: resto.reduce(function (s, l) { return s + l.quantidade; }, 0),
        resto: true,
      }]);
    }
    var serie = cor('--viz-serie');
    var escolhidas = dados.naturezas || [];
    var maior = Math.max.apply(null, linhas.map(function (l) { return l.total; }).concat([1]));
    caixa.style.height = Math.max(150, linhas.length * 28 + 16) + 'px';

    return new Chart(caixa.querySelector('canvas'), {
      type: 'bar',
      plugins: [rotulos],
      data: {
        labels: linhas.map(function (l) { return l.rotulo; }),
        datasets: [{
          data: linhas.map(function (l) { return l.total; }),
          backgroundColor: linhas.map(function (l) {
            return !escolhidas.length || escolhidas.indexOf(l.rotulo) >= 0 ? serie : serie + '55';
          }),
          borderRadius: 3,
          barThickness: 16,
        }],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 250 },
        scales: {
          x: { display: false, beginAtZero: true, max: maior * 1.28 },
          y: {
            border: { display: false },
            grid: { display: false },
            ticks: {
              color: cor('--ink-suave'),
              font: { size: 10.5 },
              autoSkip: false,
              callback: function (valor) {
                var texto = this.getLabelForValue(valor);
                var maximo = caixa.clientWidth < 480 ? 16 : 28;
                return texto.length > maximo ? texto.slice(0, maximo - 1) + '…' : texto;
              },
            },
          },
        },
        plugins: {
          legend: { display: false },
          rotulos: { ligado: true },
          tooltip: dica(function (item) {
            var linha = linhas[item.dataIndex];
            return [
              moeda.format(item.raw),
              (item.raw / total * 100).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + '% do recorte',
              linha.quantidade.toLocaleString('pt-BR') + ' lançamentos',
            ];
          }),
        },
        onHover: ponteiro,
        onClick: function (_evento, itens) {
          if (!itens.length) return;
          var linha = linhas[itens[0].index];
          if (linha.resto) return;
          irPara(function (p) {
            var atuais = p.getAll('natureza');
            p.delete('natureza');
            var novas = atuais.indexOf(linha.rotulo) >= 0
              ? atuais.filter(function (n) { return n !== linha.rotulo; })
              : atuais.concat([linha.rotulo]);
            novas.forEach(function (n) { p.append('natureza', n); });
          });
        },
      },
    });
  }

  function tempo(caixa, dados) {
    var pontos = dados.tempo;
    var ver = caixa.getAttribute('data-ver');
    var modo = document.querySelector('[data-modo-tempo]');
    var acumulado = modo && modo.value === 'acumulado';
    var valores = pontos.map(function (p) { return p.total; });
    if (acumulado) {
      var soma = 0;
      valores = valores.map(function (v) { return (soma += v); });
    }
    var algumEscolhido = pontos.some(function (p) { return p.escolhido; });
    var serie = cor('--viz-serie');
    var largura = caixa.clientWidth / Math.max(pontos.length, 1);

    return new Chart(caixa.querySelector('canvas'), {
      type: 'bar',
      plugins: [rotulos],
      data: {
        labels: pontos.map(function (p) { return p.rotulo; }),
        datasets: [{
          data: valores,
          backgroundColor: pontos.map(function (p) {
            return !algumEscolhido || p.escolhido ? serie : serie + '55';
          }),
          borderRadius: 3,
          maxBarThickness: 44,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 250 },
        layout: { padding: { top: 18 } },
        scales: {
          x: {
            border: { display: false },
            grid: { display: false },
            ticks: { color: cor('--muted'), font: { size: 11 } },
          },
          y: {
            beginAtZero: true,
            border: { display: false },
            grid: { color: cor('--viz-grade'), drawTicks: false },
            ticks: { color: cor('--muted'), font: { size: 10.5 }, maxTicksLimit: 5, padding: 6, callback: curto },
          },
        },
        plugins: {
          legend: { display: false },
          rotulos: { ligado: largura >= 44 },
          tooltip: dica(function (item) {
            return moeda.format(item.raw) + (acumulado ? ' acumulado' : '');
          }),
        },
        onHover: ver === 'dia' ? null : ponteiro,
        onClick: function (_evento, itens) {
          if (!itens.length || ver === 'dia') return;
          var ponto = pontos[itens[0].index];
          irPara(function (p) {
            if (ponto.escolhido) {
              p.delete('inicio');
              p.delete('fim');
              return;
            }
            p.set('inicio', ponto.inicio);
            p.set('fim', ponto.fim);
            // Do ano clicado, o gráfico passa a mostrar os meses dele.
            if (ver === 'ano') {
              p.set('ver', 'mes');
              p.set('ano', ponto.titulo);
            }
          });
        },
      },
    });
  }

  function desenhar() {
    var fonte = document.getElementById('dados-graficos');
    if (!fonte || !window.Chart) return;
    var dados = JSON.parse(fonte.textContent);

    graficos.forEach(function (g) { g.destroy(); });
    graficos = [];
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;

    var caixaNatureza = document.querySelector('[data-grafico=natureza]');
    var caixaTempo = document.querySelector('[data-grafico=tempo]');
    if (caixaNatureza) graficos.push(natureza(caixaNatureza, dados));
    if (caixaTempo) graficos.push(tempo(caixaTempo, dados));
  }

  document.addEventListener('DOMContentLoaded', function () {
    desenhar();

    var modo = document.querySelector('[data-modo-tempo]');
    if (modo) modo.addEventListener('change', desenhar);

    // Troca de tema muda as cores do canvas, que não segue o CSS sozinho.
    new MutationObserver(desenhar).observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    });
    if (window.matchMedia) {
      window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', desenhar);
    }
  });
})();
