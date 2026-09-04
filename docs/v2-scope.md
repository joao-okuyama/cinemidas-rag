# CineMidas v2 — Escopo do agente conversacional de ingressos

## 1. Visão geral

O CineMidas v2 é uma evolução do assistente de perguntas frequentes da Rede CineViva.

Nesta versão, o CineMidas será um agente conversacional capaz de ajudar um usuário a descobrir filmes, escolher uma unidade, selecionar uma sessão, reservar assentos e concluir uma compra simulada.

A Rede CineViva, suas unidades, sessões, preços, assentos, pedidos e pagamentos são fictícios e foram criados exclusivamente para fins educacionais.

## 2. Objetivo

Permitir que o usuário percorra uma jornada simulada de compra de ingressos utilizando linguagem natural.

Exemplos:

- “Quais filmes estão passando perto de mim?”
- “Quero assistir A Odisseia amanhã à noite.”
- “Tem alguma sessão legendada?”
- “Quero dois lugares juntos no meio da sala.”
- “Vou pagar um ingresso inteiro e uma meia-entrada.”
- “Quero pagar por PIX.”
- “Qual é o horário do meu filme de amanhã?”
- “Mostre meus ingressos recentes.”

## 3. Princípio de arquitetura

O modelo de linguagem será responsável por:

- Interpretar a intenção do usuário.
- Extrair informações da conversa.
- Escolher a ferramenta adequada.
- Apresentar os resultados de forma natural.
- Solicitar informações que ainda estiverem ausentes.

O modelo de linguagem não será responsável por:

- Inventar filmes, cinemas ou sessões.
- Determinar a disponibilidade real de um assento.
- Alterar preços.
- Calcular descontos ou totais.
- Confirmar pagamentos por conta própria.
- Criar pedidos sem validação.
- Ignorar regras comerciais definidas pela aplicação.

Sessões, assentos, reservas, preços, descontos, pagamentos e pedidos serão controlados por serviços determinísticos da aplicação.

## 4. Escopo do MVP

A primeira versão funcional do CineMidas v2 deverá possuir:

### 4.1 Descoberta de filmes

- Catálogo com títulos reais de filmes.
- Sinopse, gênero, duração e classificação indicativa.
- Pesquisa por título.
- Listagem de filmes em cartaz.
- Ordenação opcional por popularidade.

### 4.2 Localização

- Solicitação da cidade ou do bairro do usuário.
- Listagem de unidades CineViva disponíveis.
- Distância aproximada quando houver coordenadas suficientes.
- Possibilidade de alterar a localização durante a conversa.

A primeira versão não tentará descobrir silenciosamente a localização exata do usuário.

### 4.3 Cinemas e sessões

- Três unidades fictícias da Rede CineViva.
- Salas Standard, VIP, 3D e IMAX.
- Sessões simuladas para os próximos sete dias.
- Opções dubladas e legendadas.
- Horários e preços definidos pela aplicação.
- Identificação da sala e do formato da sessão.

### 4.4 Seleção de assentos

- Mapa simulado com fileiras de A até J.
- Assentos numerados de 1 até 12.
- Estados disponível, ocupado, reservado temporariamente e selecionado.
- Seleção direta, como “F6 e F7”.
- Recomendação conversacional, como “dois lugares juntos no meio”.
- Validação de disponibilidade antes da reserva.
- Reserva temporária dos assentos por cinco minutos.
- Sugestão de alternativas quando os assentos solicitados não estiverem disponíveis.

### 4.5 Preços e descontos

- Ingresso inteiro.
- Meia-entrada simulada.
- Taxa de conveniência.
- Resumo discriminado dos valores.
- Cálculos realizados em centavos por regras determinísticas.
- Aviso de que a comprovação da meia-entrada seria exigida em um cenário real.

### 4.6 Pagamento simulado

- PIX simulado.
- Cartão de crédito simulado.
- Pontos fictícios do CineViva Club.
- Nenhum pagamento financeiro real.
- Nenhuma solicitação ou armazenamento de número real de cartão, CVV, senha ou dado bancário.
- Códigos PIX sem validade financeira.
- Identificadores de pagamento claramente marcados como simulação.

### 4.7 Pedido e ingresso

- Código alfanumérico de reserva.
- Ingresso digital simulado.
- Identificação do filme, cinema, sala, data, horário e assentos.
- Placeholder de QR Code sem validade.
- Histórico persistente de pedidos simulados por `user_id`.
- Consulta de ingressos futuros.
- Consulta de pedidos recentes.

### 4.8 Perguntas frequentes

O RAG da versão 1 continuará disponível como uma ferramenta especializada para responder perguntas sobre:

- Cancelamentos.
- Reembolsos.
- Pagamentos.
- Meia-entrada.
- Acessibilidade.
- Alimentos.
- Programa de fidelidade.
- Canais de atendimento.

## 5. Fontes de dados

### 5.1 Dados reais

Poderão ser utilizados provedores autorizados para obter:

- Títulos.
- Sinopses.
- Gêneros.
- Duração.
- Classificação indicativa.
- Imagens de divulgação.
- Popularidade.

A fonte utilizada deverá ser identificada e suas condições de uso deverão ser respeitadas.

### 5.2 Dados simulados

Inicialmente, serão simulados:

- Unidades CineViva.
- Salas.
- Programação específica da CineViva.
- Horários.
- Preços.
- Assentos.
- Disponibilidade.
- Reservas.
- Pagamentos.
- Pedidos.
- Pontos de fidelidade.
- Ingressos e vouchers.

Filmes reais não significam que as sessões simuladas representam a programação de uma rede de cinemas real.

### 5.3 Ingresso.com

A integração com a API de conteúdo da Ingresso.com dependerá de acesso autorizado e código de parceiro.

O projeto não utilizará scraping nem apresentará uma integração não autorizada como funcionalidade concluída.

## 6. Estados da conversa

A jornada de compra poderá passar pelos seguintes estados:

1. `NEW`
2. `AWAITING_LOCATION`
3. `BROWSING_MOVIES`
4. `AWAITING_CINEMA`
5. `AWAITING_SESSION`
6. `AWAITING_SEATS`
7. `SEATS_HELD`
8. `AWAITING_TICKET_TYPES`
9. `CHECKOUT`
10. `AWAITING_PAYMENT`
11. `CONFIRMED`

Estados excepcionais:

- `HOLD_EXPIRED`
- `SOLD_OUT`
- `PAYMENT_FAILED`
- `CANCELLED`

O estado será controlado pela aplicação e não apenas pelo histórico textual enviado ao modelo.

## 7. Persistência

O MVP utilizará uma base SQLite para armazenar:

- Usuários simulados.
- Cinemas.
- Salas.
- Filmes.
- Sessões.
- Assentos.
- Reservas temporárias.
- Pedidos.
- Pagamentos simulados.
- Ingressos.

O arquivo da base deverá ser armazenado fora da camada descartável do contêiner, utilizando persistência apropriada no ambiente de deploy.

## 8. Canais

### Canal inicial

- Aplicação web.

### Canais futuros

- Telegram.
- WhatsApp.
- Outros clientes capazes de consumir a API da aplicação.

A lógica comercial será independente do canal. Cada canal será responsável apenas por transformar as respostas estruturadas em texto, botões, listas, cartões ou componentes visuais.

## 9. Fora do escopo do MVP

Não fazem parte do MVP:

- Venda de ingressos reais.
- Cobrança financeira real.
- Integração com adquirentes ou bancos.
- Armazenamento de cartões.
- Consulta de clientes reais.
- Programa de fidelidade real.
- Cancelamento ou reembolso real.
- Autenticação corporativa.
- Integração não autorizada com plataformas externas.
- Aplicativos completos para WhatsApp e Telegram.
- Garantia de disponibilidade de nível produtivo.
- Uso comercial por uma rede de cinemas real.

## 10. Critérios de conclusão do MVP

O MVP será considerado funcional quando for possível:

1. Informar uma localização.
2. Consultar filmes em cartaz.
3. Escolher um filme.
4. Escolher uma unidade CineViva.
5. Selecionar uma sessão.
6. Visualizar o mapa de assentos.
7. Reservar assentos disponíveis por cinco minutos.
8. Selecionar os tipos de ingresso.
9. Calcular subtotal, descontos, taxas e total.
10. Concluir um pagamento simulado.
11. Gerar um ingresso simulado.
12. Consultar posteriormente o pedido pelo mesmo `user_id`.
13. Impedir que dois usuários confirmem o mesmo assento.
14. Responder perguntas de políticas utilizando o RAG existente.
15. Passar pelos testes funcionais e transacionais definidos para a versão 2.

## 11. Classificação do projeto

O CineMidas v2 será um protótipo educacional de agente conversacional transacional.

Mesmo quando hospedado publicamente, não deverá ser descrito como:

- Sistema de vendas em produção.
- Plataforma oficial de uma rede de cinemas.
- Serviço financeiro.
- Integração comercial com a Ingresso.com.
- Sistema capaz de emitir ingressos válidos.
