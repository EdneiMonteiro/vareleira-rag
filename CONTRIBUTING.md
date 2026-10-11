# Como contribuir

Discuta alterações de escopo, escolha de tecnologia e novos conjuntos de
documentos em [Discussions](https://github.com/EdneiMonteiro/vareleira-rag/discussions)
antes de implementá-los. Correções pontuais podem ser enviadas por pull request.
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
python -m pip install -r requirements\l200.txt
python -m unittest discover -s tests
```

Use `requirements\l100.txt` para uma cópia que contenha somente o L100.
Na entrega L300, use `requirements\l300.txt`, que reutiliza o L200.
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

No L200, os guias e o avaliador HTTP usam `dados\l200\avaliacao\chat-teste-v1.json`.
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
Isso não autoriza novas execuções ou destinos. Actions e federação não foram ativados.

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
