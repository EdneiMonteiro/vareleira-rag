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
  };
  const TEMPO_MAXIMO_MS = 100000;

  const corpo = document.body;
  const modo = corpo.dataset.modo || "";
  const limite = Number.parseInt(corpo.dataset.limitePergunta, 10) || 1000;
  const conversa = document.getElementById("conversa");
  const formulario = document.getElementById("formulario");
  const campo = document.getElementById("pergunta");
  const contador = document.getElementById("contador");
  const enviar = document.getElementById("enviar");
  const novaConversa = document.getElementById("nova-conversa");
  const avisoDoModo = document.getElementById("aviso-do-modo");

  // A conversa existe só nesta lista, na memória da página: nada é gravado no navegador, e o servidor
  // recebe apenas a pergunta atual, sem as anteriores.
  let mensagens = [];
  let aguardando = false;
  let geracao = 0;

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

  // Cada chamada leva uma pergunta e um identificador novo, gerado aqui: o servidor não guarda nem reaproveita nada.
  async function consultar(pergunta) {
    const controle = new AbortController();
    const prazo = window.setTimeout(function () {
      controle.abort();
    }, TEMPO_MAXIMO_MS);
    try {
      const resposta = await fetch("/api/perguntar", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify({ pergunta: pergunta, id: novoId() }),
        credentials: "same-origin",
        cache: "no-store",
        redirect: "manual",
        signal: controle.signal,
      });
      if (resposta.type === "opaqueredirect") {
        return falha(pergunta, MENSAGENS.sessao);
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
      return falha(pergunta, erro && erro.name === "AbortError" ? MENSAGENS.demora : MENSAGENS.rede);
    } finally {
      window.clearTimeout(prazo);
    }
  }

  function atualizarControles() {
    enviar.disabled = aguardando;
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
    const pendente = elemento("article", "mensagem assistente pendente", "Consultando os documentos…");
    conversa.append(pendente);
    rolarParaOFim();
    const resultado = await consultar(pergunta);
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

  if (AVISOS_DO_MODO[modo]) {
    avisoDoModo.textContent = AVISOS_DO_MODO[modo];
    avisoDoModo.hidden = false;
  }
  campo.maxLength = limite;
  atualizarContador();
  atualizarControles();
  campo.focus();
})();
