# Como contribuir

Discuta alterações de escopo, escolha de tecnologia e novos conjuntos de
documentos em [Discussions](https://github.com/EdneiMonteiro/vareleira-rag/discussions)
antes de implementá-los. Correções pontuais podem ser enviadas por pull request
(PR, proposta de alteração).
Procure issues e propostas existentes para evitar duplicação.

## Contexto e conteúdo

O laboratório representa o piloto interno de 2025 descrito no
[README](README.md), com contexto Vareleira 0.1.0. Preserve personagens,
responsabilidades e a distinção entre o piloto e o assessment de agosto de 2026.
Não altere retroativamente os resultados desse assessment; melhorias devem
ser alternativas ou evoluções posteriores identificadas.

Use português do Brasil, explique siglas no primeiro uso e diferencie
entregas disponíveis de propostas. Documentos de seguros devem ser
explicitamente sintéticos, com origem, produto, versão e vigência fictícia.
Não invente regras do produto como se já fossem parte do contexto publicado.

Para novos desafios, siga o [padrão de autoria](docs/guia-de-autoria.md).
O público não se limita a desenvolvedores: inclua explicações, glossário,
resultados esperados e orientação prática de GitHub Copilot no VS Code.
Use o [primeiro desafio L100](desafios/L100/01-preparar-ambiente.md) como amostra
de formato e de validação: o guia traz a situação da validação, e a pasta
[docs/validacao](docs/validacao) guarda a matriz do que foi conferido e do que não foi.

Não envie dados pessoais reais, segredos, arquivos de ambiente, resultados
com informações sensíveis ou documentos sem autorização de redistribuição.

## Envio de alterações

1. Crie uma branch ou fork e faça uma alteração de escopo delimitado.
2. Atualize a documentação e as atribuições diretamente afetadas.
3. Confira links, coerência do contexto e ausência de dados sensíveis.
4. Descreva no pull request a motivação, as mudanças e as verificações feitas.

## Verificações

Prepare o ambiente com Python 3.12 ou superior e execute, na pasta do projeto:

```powershell
python -m pip install -r requirements\l400.txt
python -m unittest discover -s tests
```

Use `requirements\l100.txt` para uma cópia que contenha somente o L100.
Para L200, use `requirements\l200.txt`; para L300, use `requirements\l300.txt`, que reutiliza o L200.
O L400 reutiliza o L300, sem acrescentar dependências diretas.
Os testes não acessam o Azure. Ao alterar o Bicep, execute também
`az bicep lint --file infra/main.bicep` (a saída deve ficar vazia: o comando termina
com código 0 mesmo com avisos) e `az bicep build --file infra/main.bicep --stdout`.
Ao editar um documento de `dados`, execute `python scripts\atualizar_hashes_inventario.py`:
ele mostra se o inventário precisa de novos hashes, e `--gravar` só deve ser usado
depois de revisar o conteúdo. Como a divisão em trechos depende do texto, confira
também `python scripts\visualizar_trechos.py` e os números citados no Desafio 02
(quantidade de trechos, `dados\l100\conferencia-recuperacao.json`). Ao alterar os conjuntos
de perguntas do Desafio 06, execute `python scripts\avaliar_respostas.py --etapa validar`.
Mantenha as perguntas de `dados\l100\avaliacao\teste.json` fora de guias, registros, instruções,
README e deste arquivo; um teste automático confere esses destinos.
Um teste de saída em `tests\test_avaliacao.py` já contém perguntas do conjunto: a independência
parcial está registrada na validação do D06. Evite ampliar essa exposição.

No L200, os guias e o avaliador do protocolo de transferência de hipertexto (HTTP) usam
`dados\l200\avaliacao\chat-teste-v1.json`.
Preserve as perguntas finais fora de guias, registros, prompts de desenvolvimento e conteúdo
recuperável. Conserve arquivo, código e configuração após a medição; correções de comportamento
precisam de casos de desenvolvimento e novo teste final. Ao alterar a infraestrutura L200,
execute `az bicep lint --file infra\l200.bicep` e `az bicep build --file infra\l200.bicep --stdout`.
Para JavaScript da interface, use `node --check web\app.js` e confira o navegador.

No L300, valide o manifesto com `python scripts\gerenciar_ingestao_l300.py --etapa validar`.
Ao alterar a infraestrutura, execute lint e build com `infra\l300.bicep`, usando Bicep 0.48.1
ou superior. `python scripts\operar_l300.py --etapa plano --fase rede --validar-bicep` confere
o plano e o template localmente, sem login. Preserve os defaults L200 e os três documentos L100;
as fontes novas exigem classificação e revisão correspondentes.
Testes com dublês e parsing de workflows não substituem login, conectividade ou execução Actions.
A rodada posterior L300 recebeu autorização específica para executar e limpar os temporários
Azure; consulte o [registro](docs/validacao/l300-azure-validacao.md).
Isso não autoriza novas execuções ou destinos. Actions e federação não foram ativados nessa rodada Azure.
A [publicação posterior](docs/validacao/publicacao-l300-l400.md) executou a integração contínua (CI)
em runners hospedados. Após os merges dos PRs #1 → #2 → #3, em 11 de outubro de 2026, a CI passou
também na principal. O workflow de implantação por GitHub Actions e OpenID Connect (OIDC,
protocolo de identidade) nunca foi executado; nenhuma confiança federada foi criada.
O login humano continua não executado. Publicar os arquivos de workflow não autoriza implantá-los.

No L400, `python scripts\operar_l400.py --etapa planejar --validar-bicep` confere o plano e
o template sem rede. Coordenação e contingência preservam acesso documental e política L100;
novas perguntas finais devem ser congeladas depois do código e fora do corpus.
O [registro L400](docs/validacao/l400-validacao.md) identifica a implementação e as verificações.
Um relatório simulado, uma guarda Bicep ou um JSON do operador não comprova execução Azure.
O cancelamento explícito L400 exige o mesmo ator autenticado e um registro limitado às
execuções ativas; não trate fechar a conexão como prova de interrupção através da borda.
O registro atual é por processo, com uma réplica. Preserve a comparação congelada da versão
que respondeu o teste final; correções operacionais posteriores recebem provas específicas.
A rodada autorizada L400 foi encerrada com ausência real dos temporários, expurgos e preservação
da linha de base conferidos. Isso não autoriza reproduzir a implantação, criar federação
ou executar o workflow de implantação.
Cobrança ainda indisponível não é custo zero.

As [ferramentas públicas desta rodada](docs/validacao/operacao-publica-l300-l400-2026-10-11.md)
acrescentam planejamento de encerramento, sondas e carga finita. Os testes automáticos usam
dublês; a [rodada Azure posterior](docs/validacao/operacao-publica-azure-validacao-2026-10-11.md)
exercitou planejador, sonda interna, carga e migração, com falhas e retomadas preservadas
e limpeza aprovada. O PR #5 foi mesclado com a correção de herdadas; o PR #6 foi mesclado
por delegação, e a pré-release `v0.4.2-l400` foi publicada com os achados e o registro.
`v0.4.1-l400` e anteriores não contêm essa evidência Azure.

**A prova é parcial e não homologa produção:** os serviços de dados ainda tinham acesso
público habilitado. Fase `isolar`, repetição posterior, negativas externas, ingresso externo,
login humano, implantação Actions/OIDC e avaliação semântica nova não foram executados.
Os helpers externos e o verificador L100 D07 corrigido não receberam nova prova Azure.
Custo efetivo indisponível não é zero; publicação não autoriza repetir ou mudar destino.
Para consultar ajuda e conferir
a preparação local sem rede, com o ambiente Python preparado, use:

```powershell
python scripts\planejar_encerramento.py --help
python scripts\sonda_l300.py --etapa validar
python scripts\montar_contexto_sonda_l300.py --help
python scripts\gerar_carga_l400.py --help
```

O planejador só imprime comandos; não executa a limpeza. A linha de base deve ser capturada
antes de criar o grupo temporário. Nunca execute etapas que alteram o Azure ou consomem modelos
sem autorização correspondente, destino explícito, orçamento e limpeza definidos.

Ao introduzir código, inclua instruções reproduzíveis, dependências com versões
fixas, testes proporcionais ao comportamento e, se houver serviços pagos, custos
e encerramento de recursos. Etapas que alteram o Azure só devem ser executadas em
ambiente autorizado, com destino explícito e simulação ou `what-if` antes. Etapas que criam
identidades, credenciais ou papéis (Desafio 07) exigem autorização de quem administra o
tenant e a assinatura. Nunca inclua identificadores do seu ambiente, como assinatura, tenant,
nome de conta ou ID de aplicação. Correções de texto usam as ferramentas existentes do projeto.

## Licenças e créditos

Ao contribuir, confirme que tem os direitos necessários e disponibilize
código sob MIT e conteúdo sob CC BY 4.0, nos escopos de [LICENSE](LICENSE).
Materiais de terceiros preservam sua licença e precisam de atribuição em
[NOTICE.md](NOTICE.md). Contribuições incorporadas seguem [CONTRIBUTORS.md](CONTRIBUTORS.md).

Respeite o [código de conduta](CODE_OF_CONDUCT.md). O mantenedor pode solicitar
ajustes ou recusar mudanças incompatíveis com o escopo e os limites do piloto.
