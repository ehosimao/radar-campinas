/* Radar Campinas: site estático, sem dependências. */
(function () {
  "use strict";
  const SAPL = "https://sapl.campinas.sp.leg.br";
  const app = document.getElementById("app");
  const cache = {};
  const GRUPOS = ["melhoria", "cobranca", "homenagem", "lei", "outros"];

  function carregar(caminho) {
    if (!cache[caminho]) {
      cache[caminho] = fetch("dados/" + caminho, { cache: "no-cache" }).then(function (r) {
        if (!r.ok) throw new Error("Não consegui carregar " + caminho);
        return r.json();
      });
    }
    return cache[caminho];
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function semAcento(s) {
    return String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  }
  function data(iso) {
    if (!iso) return "";
    const p = iso.slice(0, 10).split("-");
    return p[2] + "/" + p[1] + "/" + p[0];
  }
  function num(n) { return Number(n || 0).toLocaleString("pt-BR"); }
  function pct(a, b) { return b ? Math.round((100 * a) / b) : null; }
  function foto(v, grande) {
    const cls = "foto" + (grande ? " foto-g" : "");
    if (v.foto) return '<img class="' + cls + '" src="' + esc(v.foto) + '" alt="" loading="lazy" onerror="this.style.visibility=\'hidden\'">';
    const ini = v.nome.split(/\s+/).filter(Boolean).slice(0, 2).map(function (p) { return p[0]; }).join("");
    return '<span class="' + cls + '" aria-hidden="true">' + esc(ini) + "</span>";
  }
  function marcaNav() {
    const h = location.hash || "#/";
    document.querySelectorAll(".topo nav a").forEach(function (a) {
      const alvo = a.getAttribute("href");
      a.classList.toggle("ativo", alvo === "#/" ? (h === "#/" || h.indexOf("#/v/") === 0) : h.indexOf(alvo) === 0);
    });
  }
  function erro(e) {
    app.innerHTML = '<div class="aviso">' + esc(e.message || e) + "</div>";
  }

  /* ---------- Lista de vereadores ---------- */
  function telaLista(geral) {
    const estado = { q: "", ordem: "nome" };
    app.innerHTML =
      "<h1>O que cada vereador de Campinas faz</h1>" +
      '<p class="sub">Presença nas reuniões e propostas apresentadas desde ' + data(geral.periodo.desde) +
      ", com os dados oficiais da Câmara. Toque em um nome para ver tudo.</p>" +
      '<div class="controles"><input type="search" id="q" placeholder="Procurar vereador ou partido" aria-label="Procurar vereador">' +
      '<select id="ordem" aria-label="Ordenar"><option value="nome">Ordem alfabética</option>' +
      '<option value="presenca">Maior presença</option><option value="propostas">Mais propostas</option>' +
      '<option value="lei">Mais propostas de lei</option></select></div>' +
      '<ul class="lista" id="lista"></ul>' +
      '<div id="outros"></div>';
    function desenha() {
      const q = semAcento(estado.q);
      const lista = geral.vereadores.filter(function (v) {
        return !q || semAcento(v.nome + " " + (v.partido || "")).indexOf(q) >= 0;
      });
      const chave = {
        nome: function (a, b) { return a.nome.localeCompare(b.nome, "pt-BR"); },
        presenca: function (a, b) { return (b.presenca.pct == null ? -1 : b.presenca.pct) - (a.presenca.pct == null ? -1 : a.presenca.pct); },
        propostas: function (a, b) { return b.propostas.total - a.propostas.total; },
        lei: function (a, b) { return b.propostas.lei - a.propostas.lei; },
      }[estado.ordem];
      const atuais = lista.filter(function (v) { return v.em_exercicio; }).sort(chave);
      const antigos = lista.filter(function (v) { return !v.em_exercicio; }).sort(chave);
      document.getElementById("lista").innerHTML = atuais.map(cartao).join("") ||
        '<li class="sub">Nenhum vereador encontrado.</li>';
      document.getElementById("outros").innerHTML = antigos.length
        ? "<h2>Já passaram por esta legislatura</h2><p class=\"sub\">Suplentes e vereadores que deixaram o cargo. " +
          "Os números contam só o período em que estavam no mandato.</p><ul class=\"lista\">" +
          antigos.map(cartao).join("") + "</ul>"
        : "";
    }
    function cartao(v) {
      const p = v.presenca;
      return '<li><a class="card" href="#/v/' + v.id + '">' + foto(v) + "<div>" +
        '<div class="nome">' + esc(v.nome) + (v.titular ? "" : '<span class="selo">suplente</span>') + "</div>" +
        '<div class="partido">' + esc(v.partido || "partido não informado") + "</div>" +
        '<div class="mini"><span>Presença <b>' + (p.total ? p.pct + "%" : "sem dado") + "</b></span>" +
        "<span><b>" + num(v.propostas.total) + "</b> propostas</span>" +
        "<span><b>" + num(v.propostas.lei) + "</b> de lei</span></div>" +
        "</div></a></li>";
    }
    document.getElementById("q").addEventListener("input", function (e) { estado.q = e.target.value; desenha(); });
    document.getElementById("ordem").addEventListener("change", function (e) { estado.ordem = e.target.value; desenha(); });
    desenha();
  }

  /* ---------- Ficha do vereador ---------- */
  function telaVereador(geral, v) {
    const p = v.presenca;
    const tot = v.propostas.reduce(function (acc, x) { acc[x.g] = (acc[x.g] || 0) + 1; return acc; }, {});
    const total = v.propostas.length;
    let h = '<a class="voltar" href="#/">← Todos os vereadores</a>' +
      '<div class="cabeca">' + foto(v, true) + "<div><h1>" + esc(v.nome) + "</h1>" +
      '<div class="partido">' + esc(v.partido || "partido não informado") +
      (v.titular ? "" : ' · <span class="selo">suplente</span>') + "</div>" +
      '<div class="partido">No mandato: ' + data(v.mandato.inicio) + " a " +
      (v.em_exercicio ? "hoje" : data(v.mandato.fim)) + "</div></div></div>";

    h += '<div class="numeros">' +
      '<div class="numero"><div class="valor">' + (p.pct != null ? p.pct + "%" : "—") + "</div>" +
      '<div class="rotulo">presença nas reuniões<br>(' + num(p.presentes) + " de " + num(p.total) + ")</div>" +
      (p.pct != null ? '<div class="barra"><span style="width:' + p.pct + '%"></span></div>' : "") +
      (p.ordemdia && p.ordemdia.pct != null ? '<div class="rotulo" style="margin-top:.35rem">Na hora das votações: <b>' + p.ordemdia.pct + "%</b> (" +
        num(p.ordemdia.presentes) + " de " + num(p.ordemdia.total) + ")</div>" : "") + "</div>" +
      '<div class="numero"><div class="valor">' + num(total) + '</div><div class="rotulo">propostas apresentadas</div>' +
      '<a href="' + SAPL + "/parlamentar/" + v.id + '" rel="noopener">ver na Câmara</a></div>' +
      '<div class="numero"><div class="valor">' + num(tot.lei || 0) + '</div><div class="rotulo">propostas de lei</div></div>' +
      '<div class="numero"><div class="valor">' + num(v.votos.length) + '</div><div class="rotulo">votos registrados por nome</div></div>' +
      "</div>";

    if (v.email || v.telefone) {
      h += '<div class="info">Contato público do gabinete: ' +
        (v.email ? '<a href="mailto:' + esc(v.email) + '">' + esc(v.email) + "</a>" : "") +
        (v.email && v.telefone ? " · " : "") + esc(v.telefone || "") + "</div>";
    }

    // Presença
    h += "<h2>Presença</h2><p class=\"sub\">Contamos as reuniões ordinárias e extraordinárias em que a Câmara registrou a lista de presença " +
      "e o vereador estava no mandato. O número grande é a lista da abertura da reunião. “Na hora das votações” é a lista da Ordem do Dia, a parte em que se vota. " +
      "Reuniões sem lista registrada não entram na conta, para ninguém ser acusado de falta por erro do sistema.</p>";
    if (p.pct == null) {
      h += '<div class="info">Poucas reuniões contadas para calcular uma porcentagem.</div>';
    }
    if (p.fora && p.fora.length) {
      h += '<div class="aviso"><b>Períodos não contados (provável licença, afastamento ou antes da posse):</b><ul style="margin:.3rem 0 0;padding-left:1.1rem">' +
        p.fora.map(function (f) {
          return "<li>de " + data(f.de) + " a " + data(f.ate) + ": " + num(f.reunioes) + " reuniões seguidas fora da lista de presença</li>";
        }).join("") + "</ul><div style=\"margin-top:.3rem\">Isto é uma estimativa do site: o sistema da Câmara não registra licenças. " +
        '<a href="#/sobre">Entenda a regra</a>.</div></div>';
    }
    if (p.ausencias.length) {
      h += '<details class="grupo"><summary><span>Reuniões em que não aparece na lista de presença</span><span class="qtd">' +
        num(p.ausencias.length) + "</span></summary><ul class=\"itens\">" +
        p.ausencias.map(function (a) {
          return '<li><a href="' + SAPL + "/sessao/" + a.id + '/presenca" rel="noopener">' + esc(a.nome) + "</a>" +
            '<div class="meta">' + data(a.data) + "</div></li>";
        }).join("") + "</ul></details>";
      if (p.observacao) h += '<p class="sub">' + esc(p.observacao) + "</p>";
    } else if (p.total) {
      h += '<p class="info">Aparece na lista de presença de todas as ' + num(p.total) + " reuniões contadas.</p>";
    }

    // Propostas por grupo
    h += "<h2>Propostas</h2>";
    if (total) {
      h += '<div class="empilhada" aria-hidden="true">' + GRUPOS.map(function (g) {
        return tot[g] ? '<span class="g-' + g + '" style="width:' + (100 * tot[g] / total) + '%"></span>' : "";
      }).join("") + "</div>";
    }
    h += '<div class="grupos">' + GRUPOS.map(function (g) {
      const itens = v.propostas.filter(function (x) { return x.g === g; });
      if (!itens.length) return "";
      const info = geral.grupos[g];
      return '<details class="grupo" data-g="' + g + '"><summary><span><span class="tag g-' + g + '"></span>' +
        esc(info.nome) + '</span><span class="qtd">' + num(itens.length) + "</span></summary>" +
        '<p class="explica">' + esc(info.explicacao) + '</p><ul class="itens"></ul></details>';
    }).join("") + "</div>";

    // Votos
    h += "<h2>Como votou</h2>";
    if (v.votos.length) {
      const cont = v.votos.reduce(function (acc, x) { acc[x.voto] = (acc[x.voto] || 0) + 1; return acc; }, {});
      h += '<p class="sub">A maioria das votações na Câmara é simbólica e não registra o voto de cada um. Aqui estão só as votações em que o voto ' +
        "de cada vereador ficou registrado no sistema (" + Object.keys(cont).map(function (k) { return esc(k) + ": " + num(cont[k]); }).join(", ") + ").</p>" +
        '<details class="grupo"><summary><span>Ver votos</span><span class="qtd">' + num(v.votos.length) + '</span></summary><div style="padding:0 .9rem .6rem;overflow-x:auto"><table><thead><tr><th>Data</th><th>Matéria</th><th>Voto</th><th>Resultado</th></tr></thead><tbody>' +
        v.votos.map(function (x) {
          return "<tr><td>" + data(x.d) + '</td><td><a href="' + SAPL + "/materia/" + x.m + '" rel="noopener">' + esc(x.mn) + "</a></td>" +
            '<td class="voto-' + esc(x.voto) + '">' + esc(x.voto) + "</td><td>" + esc(x.r || "") + "</td></tr>";
        }).join("") + "</tbody></table></div></details>";
    } else {
      h += '<p class="sub">Nenhum voto por nome registrado no período. A maioria das votações na Câmara é simbólica e não registra o voto de cada vereador.</p>';
    }
    app.innerHTML = h;

    // Itens das propostas: desenhados só quando o grupo é aberto, em páginas de 50
    app.querySelectorAll("details.grupo[data-g]").forEach(function (d) {
      const g = d.getAttribute("data-g");
      const itens = v.propostas.filter(function (x) { return x.g === g; })
        .sort(function (a, b) { return (b.d || "").localeCompare(a.d || ""); });
      let mostrados = 0;
      const ul = d.querySelector(".itens");
      function mais() {
        const prox = itens.slice(mostrados, mostrados + 50);
        mostrados += prox.length;
        const velho = d.querySelector(".mais");
        if (velho) velho.remove();
        ul.insertAdjacentHTML("beforeend", prox.map(itemProposta).join(""));
        if (mostrados < itens.length) {
          const b = document.createElement("button");
          b.className = "mais"; b.type = "button";
          b.textContent = "Mostrar mais (" + num(itens.length - mostrados) + " restantes)";
          b.addEventListener("click", mais);
          ul.after(b);
        }
      }
      d.addEventListener("toggle", function () { if (d.open && !mostrados) mais(); });
    });
  }
  function itemProposta(x) {
    return '<li><a href="' + SAPL + "/materia/" + x.id + '" rel="noopener">' + esc(x.tipo) + " nº " + x.n + "/" + x.a + "</a>" +
      "<div>" + esc(x.e) + '</div><div class="meta">' + data(x.d) + (x.co ? " · com outros autores" : "") + "</div></li>";
  }

  /* ---------- Meu bairro ---------- */
  function telaBairro(geral, pedidos, termoInicial) {
    const nomes = {};
    geral.vereadores.forEach(function (v) { nomes[v.id] = v.nome; });
    app.innerHTML =
      "<h1>O que foi pedido para o seu bairro</h1>" +
      '<p class="sub">Digite o nome do bairro ou da rua. Aparecem todos os pedidos de obras e serviços (indicações e protocolados) enviados pelos vereadores à Prefeitura desde ' +
      data(geral.periodo.desde) + ".</p>" +
      '<div class="controles"><input type="search" id="q" placeholder="Ex.: Jardim Campos Elíseos ou Rua Barão de Jaguara" aria-label="Bairro ou rua"></div>' +
      '<div id="res"></div>';
    const campo = document.getElementById("q");
    const res = document.getElementById("res");
    const indice = pedidos.pedidos.map(function (p) { return semAcento(p.e); });
    function desenha() {
      const q = semAcento(campo.value.trim());
      history.replaceState(null, "", "#/bairro" + (q ? "?q=" + encodeURIComponent(campo.value.trim()) : ""));
      let h = "";
      const rec = pedidos.recorrentes.filter(function (r) { return !q || semAcento(r.local).indexOf(q) >= 0; });
      if (rec.length) {
        h += "<h2>" + (q ? "Pedidos que voltam várias vezes aqui" : "Pedidos que mais se repetem na cidade") + "</h2>" +
          '<div class="aviso">Pedido repetido não prova que a Prefeitura ignorou. Pode ser um problema que volta, um pedido feito por mais de um vereador ' +
          "ou um serviço que foi feito e precisou ser feito de novo. O site só mostra que o pedido foi feito mais de uma vez.</div>" +
          rec.slice(0, q ? 50 : 25).map(function (r) {
            return '<div class="recorrente"><div class="titulo">' + esc(r.tema) + " · " + esc(r.local) + "</div>" +
              '<div><span class="vezes">' + r.ids.length + " pedidos</span> entre " + data(r.datas[0]) + " e " + data(r.datas[r.datas.length - 1]) + "</div>" +
              '<div class="meta partido">Por: ' + r.autores.map(function (a) { return esc(nomes[a] || "outro autor"); }).join(", ") + "</div>" +
              '<details><summary class="partido" style="cursor:pointer">Ver os pedidos</summary><ul class="itens" style="padding:0">' +
              r.ids.map(function (id) { const p = pedidos.porId[id]; return p ? itemPedido(p, nomes) : ""; }).join("") +
              "</ul></details></div>";
          }).join("");
      }
      if (q.length >= 3) {
        const achados = [];
        for (let i = 0; i < indice.length; i++) if (indice[i].indexOf(q) >= 0) achados.push(pedidos.pedidos[i]);
        achados.sort(function (a, b) { return (b.d || "").localeCompare(a.d || ""); });
        const porAutor = {};
        achados.forEach(function (p) { p.v.forEach(function (a) { porAutor[a] = (porAutor[a] || 0) + 1; }); });
        h += "<h2>" + num(achados.length) + " pedidos com “" + esc(campo.value.trim()) + "”</h2>";
        if (achados.length) {
          h += '<p class="sub">Quem mais pediu: ' + Object.keys(porAutor).sort(function (a, b) { return porAutor[b] - porAutor[a]; })
            .slice(0, 6).map(function (a) { return '<a href="#/v/' + a + '">' + esc(nomes[a] || "?") + "</a> (" + porAutor[a] + ")"; }).join(", ") + "</p>" +
            '<ul class="itens" style="padding:0">' + achados.slice(0, 300).map(function (p) { return itemPedido(p, nomes); }).join("") + "</ul>" +
            (achados.length > 300 ? '<p class="sub">Mostrando os 300 mais recentes. Escreva mais detalhes para filtrar.</p>' : "");
        }
      } else if (!rec.length && q) {
        h += '<p class="sub">Digite pelo menos 3 letras.</p>';
      }
      res.innerHTML = h;
    }
    let t;
    campo.addEventListener("input", function () { clearTimeout(t); t = setTimeout(desenha, 200); });
    campo.value = termoInicial || "";
    desenha();
  }
  function itemPedido(p, nomes) {
    return '<li><a href="' + SAPL + "/materia/" + p.id + '" rel="noopener">' + esc(p.t || "Indicação") + " nº " + p.n + "/" + p.a + "</a> · " +
      p.v.map(function (a) { return '<a href="#/v/' + a + '">' + esc(nomes[a] || "?") + "</a>"; }).join(", ") +
      "<div>" + esc(p.e) + '</div><div class="meta">' + data(p.d) + "</div></li>";
  }

  /* ---------- Como funciona ---------- */
  function telaSobre(geral) {
    let h = "<h1>Como o Radar funciona</h1>" +
      "<p>O Radar Campinas mostra, com os dados oficiais da Câmara Municipal, o que cada vereador faz: se vai às reuniões, o que propõe e, quando o voto é registrado por nome, como votou. " +
      "O site não dá nota, não faz ranking de “melhor” ou “pior” e não dá opinião. Só organiza o dado e mostra de onde ele veio.</p>" +
      "<h2>De onde vêm os dados</h2><p>Do <a href=\"" + SAPL + "\" rel=\"noopener\">SAPL</a>, o sistema público da Câmara Municipal de Campinas. Um robô baixa os dados de novo toda madrugada. " +
      "Se a coleta vier incompleta ou estranha, o site continua com a última versão boa.</p>" +
      '<div class="info">Última atualização: ' + esc(geral.atualizado) + ". Período: " + data(geral.periodo.desde) + " a " + data(geral.periodo.ate) +
      " (" + esc(geral.legislatura) + ").</div>" +
      "<h2>Como as propostas são agrupadas</h2><p>Usamos a mesma regra para todos os vereadores:</p><ul>" +
      GRUPOS.map(function (g) { return "<li><b>" + esc(geral.grupos[g].nome) + ":</b> " + esc(geral.grupos[g].regra) + "</li>"; }).join("") + "</ul>" +
      "<p>Uma proposta assinada por vários vereadores conta para cada um deles. Na ficha aparece a marca “com outros autores”.</p>" +
      "<h2>Como a presença é contada</h2><p>" + esc(geral.regra_presenca) + "</p>" +
      "<h2>O que é estimativa ou tem limite</h2><ul>" + geral.limites.map(function (l) { return "<li>" + esc(l) + "</li>"; }).join("") + "</ul>" +
      "<h2>Achou um erro?</h2><p><a href=\"https://github.com/ehosimao/radar-campinas/issues/new\" rel=\"noopener\">Abra um aviso aqui</a>, dizendo qual número está errado e onde está o dado certo na Câmara. A gente confere e corrige rápido.</p>" +
      '<p class="sub">Inspirado no <a href="https://radarptlandia.org" rel="noopener">Radar de Hortolândia</a>. O código é aberto.</p>';
    app.innerHTML = h;
  }

  /* ---------- Rotas ---------- */
  function rota() {
    marcaNav();
    window.scrollTo(0, 0);
    const h = location.hash || "#/";
    carregar("geral.json").then(function (geral) {
      document.getElementById("atualizado").textContent = "Dados atualizados em " + geral.atualizado + ".";
      let m;
      if ((m = h.match(/^#\/v\/(\d+)/))) {
        app.innerHTML = '<p class="carregando">Carregando…</p>';
        return carregar("v/" + m[1] + ".json").then(function (v) {
          document.title = v.nome + " · Radar Campinas";
          telaVereador(geral, v);
        });
      }
      if (h.indexOf("#/bairro") === 0) {
        document.title = "Meu bairro · Radar Campinas";
        app.innerHTML = '<p class="carregando">Carregando os pedidos…</p>';
        const q = decodeURIComponent((h.split("?q=")[1] || "").replace(/\+/g, " "));
        return carregar("pedidos.json").then(function (pedidos) {
          if (!pedidos.porId) {
            pedidos.porId = {};
            pedidos.pedidos.forEach(function (p) { pedidos.porId[p.id] = p; });
          }
          telaBairro(geral, pedidos, q);
        });
      }
      if (h.indexOf("#/sobre") === 0) { document.title = "Como funciona · Radar Campinas"; return telaSobre(geral); }
      document.title = "Radar Campinas · o que cada vereador faz";
      telaLista(geral);
    }).catch(erro);
  }
  window.addEventListener("hashchange", function () {
    if ((location.hash || "").indexOf("#/bairro") === 0 && document.getElementById("res")) return; // digitação na busca
    rota();
  });
  rota();
})();
