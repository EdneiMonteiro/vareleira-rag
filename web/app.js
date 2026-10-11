"use strict";

(function () {
  const ROTULOS_DO_TIPO = {
    documentada: "Documentada nos trechos",
    contratacao_individual: "Contratação individual",
    sem_evidencia: "Sem evidência nos documentos",
    fora_de_escopo: "Fora de escopo",
    ambigua: "Precisa de esclarecimento",
  };
  const AVISOS_DO_MODO = {
    demonstracao: "Modo de demonstração: as respostas são simuladas e não consultam documentos nem modelos.",
    local: "Modo local sem autenticação: use somente neste computador.",
  };
  const MENSAGENS = {
    sessao: "Não foi possível confirmar a sua identidade. Recarregue a página para entrar de novo.",
    demora: "A consulta demorou mais do que o esperado. Tente de novo.",
    rede: "Não foi possível falar com o servidor. Confira a conexão e tente de novo.",
    indisponivel: "O assistente está indisponível no momento. Tente de novo em instantes.",
    generica: "Não foi possível concluir a consulta. Tente de novo.",
    cancelada: "Consulta cancelada: o servidor confirmou o cancelamento e nenhuma resposta foi produzida. Ele não começa novas etapas, " +
      "mas um pedido ao modelo que já foi enviado pode terminar e consumir tokens.",
    canceladaSemConfirmacao: "Consulta interrompida neste navegador, mas o servidor não confirmou o cancelamento: ela pode continuar até " +
      "o limite de tempo e consumir tokens. Nenhuma resposta será mostrada.",
  };
  // Com a coordenação (L400), a página acompanha as etapas por eventos que só trazem contagens: o texto da resposta
  // só chega no evento final, depois da política.
  const ROTULOS_DAS_ETAPAS = {
    planejamento: "Planejando as consultas",
    recuperacao: "Buscando só nos documentos permitidos",
    verificacao: "Conferindo versões e trechos",
    redacao: "Redigindo com referências curtas",
    politica: "Aplicando a política de resposta",
  };
  const MARCAS_DOS_ESTADOS = { iniciada: "em andamento…", concluida: "concluída", falhou: "falhou", ignorada: "não foi necessária" };
  const TEMPO_MAXIMO_MS = 100000;
  const TEMPO_MAXIMO_COORDENADO_MS = 250000;
  const TEMPO_DO_CANCELAMENTO_MS = 5000;

  const corpo = document.body;
  const modo = corpo.dataset.modo || "";
  const coordenado = corpo.dataset.coordenacao === "sim";
  const limite = Number.parseInt(corpo.dataset.limitePergunta, 10) || 1000;
  const conversa = document.getElementById("conversa");
  const formulario = document.getElementById("formulario");
  const campo = document.getElementById("pergunta");
  const contador = document.getElementById("contador");
  const enviar = document.getElementById("enviar");
  const cancelar = document.getElementById("cancelar");
  const novaConversa = document.getElementById("nova-conversa");
  const avisoDoModo = document.getElementById("aviso-do-modo");

  // A conversa existe só nesta lista, na memória da página: nada é gravado no navegador, e o servidor
  // recebe apenas a pergunta atual, sem as anteriores.
  let mensagens = [];
  let aguardando = false;
  let geracao = 0;
  let controleAtual = null;
  let canceladaPelaPessoa = false;
  // Cancelamento explícito (coordenação): o X-Request-Id da resposta do fluxo é como o servidor reconhece a consulta.
  let identificadorAtual = "";
  let cancelando = false;
  let cancelamentoConfirmado = false;

  // Todo texto vindo do servidor entra na página somente por textContent: nunca é interpretado como marcação.
  function elemento(tag, classe, texto) {
    const no = document.createElement(tag);
    if (classe) {
      no.className = classe;
    }
    if (texto !== undefined && texto !== null) {
      no.textContent = String(texto);
    }
    return no;
  }

  function novoId() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    const bytes = new Uint8Array(16);
    window.crypto.getRandomValues(bytes);
    return Array.from(bytes, function (valor) {
      return valor.toString(16).padStart(2, "0");
    }).join("");
  }

  function rolarParaOFim() {
    conversa.scrollTop = conversa.scrollHeight;
  }

  function descreverOrigem(evidencia) {
    const partes = [
      evidencia.documento,
      evidencia.secao,
      evidencia.clausulas ? "cláusulas " + evidencia.clausulas : "",
      evidencia.versao ? "versão " + evidencia.versao : "",
      evidencia.fonte,
    ].filter(Boolean);
    return partes.join(" · ") + (evidencia.id ? " (trecho " + evidencia.id + ")" : "");
  }

  function descreverUso(uso) {
    if (!uso) {
      return "";
    }
    const numero = new Intl.NumberFormat("pt-BR");
    return "Uso: " + numero.format(uso.tokens_embeddings) + " tokens na busca; " +
      numero.format(uso.tokens_entrada) + " de entrada e " + numero.format(uso.tokens_saida) +
      " de saída na resposta (" + numero.format(uso.tokens_raciocinio) + " de raciocínio).";
  }

  function desenharEvidencias(evidencias) {
    const bloco = elemento("div", "evidencias");
    bloco.append(elemento("p", "subtitulo", "Evidências conferidas nos documentos"));
    const lista = elemento("ol", "lista-de-evidencias");
    evidencias.forEach(function (evidencia) {
      const item = elemento("li");
      item.append(elemento("blockquote", "citacao", evidencia.citacao), elemento("p", "origem", descreverOrigem(evidencia)));
      lista.append(item);
    });
    bloco.append(lista);
    return bloco;
  }

  function desenharPessoa(mensagem) {
    const no = elemento("article", "mensagem pessoa");
    no.append(elemento("p", "papel", "Você"), elemento("p", "texto", mensagem.texto));
    return no;
  }

  function desenharResposta(mensagem) {
    const resposta = mensagem.resposta;
    const no = elemento("article", "mensagem assistente");
    no.append(elemento("p", "papel", "Assistente"));
    if (resposta.simulada) {
      no.append(elemento("p", "simulacao", resposta.aviso_simulacao || "Resposta simulada."));
    }
    no.append(elemento("p", "tipo", ROTULOS_DO_TIPO[resposta.tipo] || "Resposta"));
    no.append(elemento("p", "texto", resposta.texto));
    if (resposta.aviso) {
      no.append(elemento("p", "aviso", resposta.aviso));
    }
    if (Array.isArray(resposta.evidencias) && resposta.evidencias.length > 0) {
      no.append(desenharEvidencias(resposta.evidencias));
    }
    const uso = descreverUso(resposta.uso);
    if (uso) {
      no.append(elemento("p", "uso", uso));
    } else if (coordenado && !resposta.simulada) {
      no.append(elemento("p", "uso", "Uso de tokens incerto: ao menos uma tentativa ao modelo não informou o consumo."));
    }
    return no;
  }

  function desenharErro(mensagem) {
    const no = elemento("article", "mensagem erro");
    no.append(elemento("p", "papel", "Aviso"), elemento("p", "texto", mensagem.texto));
    if (mensagem.codigo) {
      no.append(elemento("p", "uso", "Código de suporte: " + mensagem.codigo));
    }
    if (mensagem.pergunta) {
      const repetir = elemento("button", "secundario", "Tentar de novo");
      repetir.type = "button";
      repetir.addEventListener("click", function () {
        perguntar(mensagem.pergunta);
      });
      no.append(repetir);
    }
    return no;
  }

  function desenhar(mensagem) {
    if (mensagem.papel === "pessoa") {
      return desenharPessoa(mensagem);
    }
    return mensagem.papel === "assistente" ? desenharResposta(mensagem) : desenharErro(mensagem);
  }

  function falha(pergunta, texto, codigo) {
    return { papel: "erro", pergunta: pergunta, texto: texto, codigo: typeof codigo === "string" ? codigo : "" };
  }

  function textoDaFalha(status, dados) {
    if (dados && typeof dados.mensagem === "string") {
      return dados.mensagem;
    }
    if (status === 401 || status === 403) {
      return MENSAGENS.sessao;
    }
    return status >= 500 ? MENSAGENS.indisponivel : MENSAGENS.generica;
  }

  // Interpreta um bloco do fluxo de progresso ("event: nome" e "data: {json}") e entrega o nome e os dados. Dados que não
  // são JSON são ignorados.
  function interpretarBloco(bloco, aoEvento) {
    let nome = "";
    const dados = [];
    bloco.split("\n").forEach(function (linha) {
      if (linha.startsWith("event:")) {
        nome = linha.slice(6).trim();
      } else if (linha.startsWith("data:")) {
        dados.push(linha.slice(5).trim());
      }
    });
    if (!nome || dados.length === 0) {
      return;
    }
    try {
      aoEvento(nome, JSON.parse(dados.join("\n")));
    } catch (erro) {
      // evento ilegível: o fluxo segue com os próximos
    }
  }

  // O progresso usa POST (o EventSource só aceita GET), então o corpo da resposta é lido aos pedaços.
  async function lerFluxo(resposta, aoEvento) {
    const leitor = resposta.body.getReader();
    const decodificador = new TextDecoder("utf-8");
    let pendente = "";
    for (;;) {
      const parte = await leitor.read();
      if (parte.done) {
        break;
      }
      pendente += decodificador.decode(parte.value, { stream: true });
      let fim = pendente.indexOf("\n\n");
      while (fim >= 0) {
        interpretarBloco(pendente.slice(0, fim), aoEvento);
        pendente = pendente.slice(fim + 2);
        fim = pendente.indexOf("\n\n");
      }
    }
  }

  // O servidor identifica cada consulta pelo X-Request-Id da resposta: com ele, e só na mesma conta, o pedido de cancelamento a alcança.
  function identificadorDaResposta(resposta) {
    const valor = resposta.headers.get("X-Request-Id") || "";
    return /^[0-9a-f]{32}$/.test(valor) ? valor : "";
  }

  // Cada chamada leva uma pergunta e um identificador novo, gerado aqui: o servidor não guarda nem reaproveita nada.
  // Com a coordenação, o mesmo envio vai para a rota de progresso e a resposta chega como eventos.
  async function consultar(pergunta, aoEvento) {
    const controle = new AbortController();
    controleAtual = controle;
    canceladaPelaPessoa = false;
    cancelando = false;
    cancelamentoConfirmado = false;
    identificadorAtual = "";
    const prazo = window.setTimeout(function () {
      controle.abort();
    }, coordenado ? TEMPO_MAXIMO_COORDENADO_MS : TEMPO_MAXIMO_MS);
    try {
      const resposta = await fetch(coordenado ? "/api/perguntar/progresso" : "/api/perguntar", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": coordenado ? "text/event-stream" : "application/json" },
        body: JSON.stringify({ pergunta: pergunta, id: novoId() }),
        credentials: "same-origin",
        cache: "no-store",
        redirect: "manual",
        signal: controle.signal,
      });
      if (resposta.type === "opaqueredirect") {
        return falha(pergunta, MENSAGENS.sessao);
      }
      if (coordenado) {
        identificadorAtual = identificadorDaResposta(resposta);
      }
      const tipoDoCorpo = resposta.headers.get("Content-Type") || "";
      if (coordenado && resposta.ok && resposta.body && tipoDoCorpo.startsWith("text/event-stream")) {
        let final = null;
        await lerFluxo(resposta, function (nome, dados) {
          if (nome === "resposta" && dados && typeof dados.texto === "string") {
            final = { papel: "assistente", resposta: dados };
          } else if (nome === "erro" && dados) {
            final = falha(pergunta, textoDaFalha(0, dados), dados.id_requisicao);
          } else if (aoEvento) {
            aoEvento(nome, dados);
          }
        });
        return final || falha(pergunta, MENSAGENS.generica);
      }
      let dados = null;
      try {
        dados = await resposta.json();
      } catch (erro) {
        dados = null;
      }
      if (resposta.ok && dados && typeof dados.texto === "string") {
        return { papel: "assistente", resposta: dados };
      }
      return falha(pergunta, textoDaFalha(resposta.status, dados), dados && dados.id_requisicao);
    } catch (erro) {
      if (erro && erro.name === "AbortError") {
        if (!canceladaPelaPessoa) {
          return falha(pergunta, MENSAGENS.demora);
        }
        return falha(pergunta, cancelamentoConfirmado ? MENSAGENS.cancelada : MENSAGENS.canceladaSemConfirmacao);
      }
      return falha(pergunta, MENSAGENS.rede);
    } finally {
      window.clearTimeout(prazo);
      controleAtual = null;
      identificadorAtual = "";
      cancelando = false;
    }
  }

  // Com a coordenação, a desconexão pode não chegar ao servidor a tempo pela borda da plataforma. Por isso, quando a página já tem o
  // identificador da consulta, o pedido de cancelamento vai PRIMEIRO ao servidor (autenticado como qualquer outra requisição), e só
  // depois a conexão é abortada. Antes de o servidor responder não há identificador: só dá para abortar aqui, sem avisá-lo.
  async function cancelarConsulta() {
    const controle = controleAtual;
    if (!controle || cancelando) {
      return;
    }
    cancelando = true;
    canceladaPelaPessoa = true;
    atualizarControles();
    const alvo = identificadorAtual;
    if (coordenado && alvo) {
      const limiteDoPedido = new AbortController();
      const espera = window.setTimeout(function () {
        limiteDoPedido.abort();
      }, TEMPO_DO_CANCELAMENTO_MS);
      try {
        const resposta = await fetch("/api/perguntar/cancelar", {
          method: "POST",
          headers: { "Content-Type": "application/json", "Accept": "application/json" },
          body: JSON.stringify({ id_requisicao: alvo }),
          credentials: "same-origin",
          cache: "no-store",
          redirect: "manual",
          signal: limiteDoPedido.signal,
        });
        cancelamentoConfirmado = controleAtual === controle && resposta.status === 202;
      } catch (erro) {
        cancelamentoConfirmado = false;
      } finally {
        window.clearTimeout(espera);
      }
    }
    controle.abort();
  }

  function criarPainelDeProgresso() {
    const no = elemento("article", "mensagem assistente pendente");
    no.append(elemento("p", "papel", "Assistente"), elemento("p", "texto", "Consultando os documentos…"));
    const lista = elemento("ul", "progresso");
    const itens = {};
    Object.keys(ROTULOS_DAS_ETAPAS).forEach(function (etapa) {
      const item = elemento("li", "etapa", ROTULOS_DAS_ETAPAS[etapa]);
      itens[etapa] = item;
      lista.append(item);
    });
    const nota = elemento("p", "uso");
    no.append(lista, nota);
    return {
      no: no,
      atualizar: function (nome, dados) {
        if (!dados || typeof dados !== "object") {
          return;
        }
        if (nome === "etapa" && itens[dados.etapa]) {
          itens[dados.etapa].className = "etapa " + String(dados.estado);
          itens[dados.etapa].textContent = ROTULOS_DAS_ETAPAS[dados.etapa] + ": " + (MARCAS_DOS_ESTADOS[dados.estado] || "");
        } else if (nome === "tentativa" && dados.estado === "falha_transitoria") {
          nota.textContent = "Uma tentativa ao modelo teve uma falha transitória; o serviço pode usar a contingência, dentro dos limites.";
        }
      },
    };
  }

  function atualizarControles() {
    enviar.disabled = aguardando;
    cancelar.hidden = !(coordenado && aguardando);
    cancelar.disabled = cancelando;
    formulario.setAttribute("aria-busy", aguardando ? "true" : "false");
  }

  function atualizarContador() {
    contador.textContent = campo.value.length + " / " + limite;
  }

  async function perguntar(texto) {
    const pergunta = String(texto).trim();
    if (aguardando) {
      return;
    }
    if (!pergunta) {
      campo.focus();
      return;
    }
    const minhaGeracao = geracao;
    const pessoa = { papel: "pessoa", texto: pergunta };
    if (pergunta.length > limite) {
      const excesso = falha("", "A pergunta tem mais de " + limite + " caracteres. Resuma-a.");
      mensagens.push(pessoa, excesso);
      conversa.append(desenharPessoa(pessoa), desenharErro(excesso));
      rolarParaOFim();
      return;
    }
    aguardando = true;
    atualizarControles();
    mensagens.push(pessoa);
    conversa.append(desenharPessoa(pessoa));
    const painel = coordenado ? criarPainelDeProgresso() : null;
    const pendente = painel ? painel.no : elemento("article", "mensagem assistente pendente", "Consultando os documentos…");
    conversa.append(pendente);
    rolarParaOFim();
    const resultado = await consultar(pergunta, painel ? painel.atualizar : null);
    if (minhaGeracao !== geracao) {
      return;
    }
    aguardando = false;
    atualizarControles();
    mensagens.push(resultado);
    pendente.replaceWith(desenhar(resultado));
    rolarParaOFim();
    campo.focus();
  }

  function enviarPergunta() {
    const texto = campo.value;
    if (aguardando || !texto.trim()) {
      campo.focus();
      return;
    }
    campo.value = "";
    atualizarContador();
    perguntar(texto);
  }

  function reiniciar() {
    cancelarConsulta();
    geracao += 1;
    mensagens = [];
    aguardando = false;
    atualizarControles();
    conversa.replaceChildren();
    campo.focus();
  }

  formulario.addEventListener("submit", function (evento) {
    evento.preventDefault();
    enviarPergunta();
  });
  campo.addEventListener("keydown", function (evento) {
    if (evento.key === "Enter" && !evento.shiftKey && !evento.isComposing) {
      evento.preventDefault();
      enviarPergunta();
    }
  });
  campo.addEventListener("input", atualizarContador);
  novaConversa.addEventListener("click", reiniciar);
  cancelar.addEventListener("click", cancelarConsulta);

  if (AVISOS_DO_MODO[modo]) {
    avisoDoModo.textContent = AVISOS_DO_MODO[modo];
    avisoDoModo.hidden = false;
  }
  campo.maxLength = limite;
  atualizarContador();
  atualizarControles();
  campo.focus();
})();
