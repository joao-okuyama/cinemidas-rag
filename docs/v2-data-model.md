# CineMidas v2 — Modelo de dados

## 1. Objetivo

Definir a estrutura de persistência do simulador de compra de ingressos.

O banco armazenará o catálogo, a programação, a disponibilidade dos assentos, as reservas temporárias, os pedidos e os pagamentos simulados.

O histórico textual da conversa não será a fonte de verdade para preços, disponibilidade ou confirmação de compras.

## 2. Tecnologia

O MVP utilizará SQLite.

Configurações previstas:

- Integridade referencial habilitada com `PRAGMA foreign_keys = ON`.
- Modo WAL para melhorar a convivência entre leituras e escritas.
- Tempo de espera limitado para operações concorrentes.
- Transações curtas para alterações de disponibilidade.
- Arquivo persistido em volume Docker.
- Banco de desenvolvimento separado do banco da aplicação publicada.

A base não será enviada ao GitHub.

O repositório conterá apenas o esquema, os scripts de inicialização e os dados fictícios necessários para criar uma base nova.

## 3. Convenções

### Identificadores

- Entidades possuem identificadores estáveis.
- Nomes e títulos não serão usados como chaves.
- IDs de provedores externos serão armazenados separadamente dos IDs internos.

### Valores monetários

Todos os valores serão armazenados em centavos inteiros.

Exemplo:

- R$ 32,50 será armazenado como `3250`.
- Não utilizar `float` para cálculos financeiros.

### Datas e horários

- Instantes serão armazenados em UTC, em formato padronizado.
- Cada cinema terá um fuso horário.
- A interface converterá os horários para o fuso do cinema.
- Expressões como “amanhã” serão interpretadas considerando o fuso e a data atual.

### Dados simulados

Pedidos, reservas e pagamentos serão sempre identificados como simulação.

## 4. Entidades

| Tabela | Finalidade | Campos principais |
|---|---|---|
| users | Identificação do usuário do simulador | user_id, created_at |
| cinemas | Unidades CineViva | cinema_id, name, city, state, region, timezone, latitude, longitude |
| rooms | Salas vinculadas às unidades | room_id, cinema_id, name, category |
| room_formats | Projeções suportadas por cada sala | room_id, projection_format |
| seats | Posições físicas de uma sala | seat_id, room_id, row_label, seat_number |
| movies | Metadados dos filmes | movie_id, provider, provider_movie_id, title, synopsis, runtime_minutes, age_rating, source_updated_at |
| sessions | Programação e preços de referência | session_id, movie_id, room_id, starts_at, ends_at, room_available_at, projection_format, audio_version, status, full_price_cents, convenience_fee_cents |
| seat_holds | Reservas temporárias | hold_id, user_id, session_id, status, created_at, expires_at |
| session_seats | Disponibilidade dos assentos por sessão | session_id, seat_id, status, hold_id, order_id |
| orders | Resumo e situação dos pedidos | order_id, user_id, session_id, hold_id, status, booking_code, subtotal_cents, discount_cents, fee_cents, total_cents, created_at, confirmed_at |
| order_items | Assentos e ingressos de cada pedido | order_item_id, order_id, seat_id, ticket_type, base_price_cents, discount_cents, fee_cents, total_cents, ticket_code |
| payments | Tentativas de pagamento simulado | payment_id, order_id, method, status, amount_cents, idempotency_key, mock_reference, created_at |
| conversation_sessions | Estado estruturado da conversa | conversation_id, user_id, channel, state, selected_movie_id, selected_cinema_id, selected_session_id, active_hold_id, active_order_id, updated_at |

Latitude, longitude e classificação indicativa poderão permanecer ausentes quando não houver informação validada.

Informação ausente não deverá ser substituída por um valor inventado.

## 5. Identidade e isolamento de usuários

O `user_id` será determinado pelo backend a partir de uma sessão validada.

O modelo de linguagem e o texto enviado pelo usuário não poderão escolher livremente qual identidade utilizar para consultar pedidos.

Regras:

- Um usuário só poderá consultar seus próprios pedidos.
- Um código de reserva, isoladamente, não autorizará acesso ao pedido.
- Não serão solicitados CPF, documento, dados bancários ou cartão real.
- O MVP web utilizará uma identidade de visitante persistente, associada a uma credencial de sessão.
- Em um novo navegador ou após perder essa credencial, o histórico não será recuperado automaticamente.
- Login e recuperação de conta ficam para uma evolução posterior.

## 6. Assentos e disponibilidade

### Identificação física

A combinação abaixo deverá ser única:

- room_id
- row_label
- seat_number

### Disponibilidade por sessão

A combinação abaixo deverá ser única:

- session_id
- seat_id

Estados de `session_seats`:

- AVAILABLE: disponível.
- HELD: reservado temporariamente.
- BOOKED: confirmado em um pedido.

“Selecionado” será uma representação visual de um assento reservado pelo usuário atual, não um estado global separado.

### Consistência

- O assento deve pertencer à sala da sessão.
- AVAILABLE não pode manter vínculo com reserva ou pedido.
- HELD deve estar vinculado a uma reserva ativa.
- BOOKED deve estar vinculado a um pedido confirmado.

Essas regras serão aplicadas por restrições do banco e validações transacionais do backend.

## 7. Reservas temporárias

Estados de `seat_holds`:

- ACTIVE.
- EXPIRED.
- RELEASED.
- CONVERTED.

O prazo será de 300 segundos a partir da criação.

Regras:

1. Verificar todos os assentos solicitados.
2. Reservar todos na mesma transação.
3. Se um deles estiver indisponível, não reservar nenhum.
4. Não estender o prazo apenas porque o usuário enviou outra mensagem.
5. Validar o vencimento em cada operação de checkout.
6. Liberar os assentos quando a reserva expirar ou for abandonada.
7. Converter a reserva somente após confirmação do pagamento simulado.

A expiração deverá ser verificada no backend, mesmo que o navegador esteja fechado.

A limpeza periódica poderá auxiliar a liberação, mas a correção não dependerá apenas de um temporizador em segundo plano.

## 8. Pedidos e preços

Estados de `orders`:

- DRAFT.
- AWAITING_PAYMENT.
- CONFIRMED.
- EXPIRED.
- CANCELLED.

Fórmula do pedido:

total_cents = subtotal_cents - discount_cents + fee_cents

O pedido armazenará os valores apresentados ao usuário no checkout.

Mudanças posteriores na tabela de preços não alterarão pedidos já confirmados.

Regras:

- O tipo de ingresso será definido por assento.
- Descontos serão calculados por funções determinísticas.
- Arredondamento e incidência das taxas serão definidos nas regras de preços.
- O modelo não poderá fornecer ou sobrescrever o total.
- Alterações no carrinho exigirão um novo resumo antes da confirmação.
- Pedidos confirmados preservarão os dados essenciais do ingresso, como título, unidade, sala, horário e assentos.

## 9. Pagamentos simulados

Métodos previstos:

- PIX_MOCK.
- CARD_MOCK.
- LOYALTY_MOCK.

Estados:

- PENDING.
- SUCCEEDED.
- FAILED.
- CANCELLED.

Regras:

- Nenhuma integração financeira real.
- Nenhum número de cartão ou CVV armazenado.
- Identificadores claramente marcados como simulação.
- Uma chave de idempotência única por operação.
- Repetir uma confirmação não poderá gerar outro pedido, ingresso ou débito.
- O valor confirmado deverá corresponder ao total do pedido.
- Uma reserva vencida não poderá ser confirmada.

A confirmação do pagamento simulado, a confirmação do pedido e a ocupação dos assentos deverão ocorrer de forma atômica.

## 10. Pontos de fidelidade

A implementação de pontos utilizará duas entidades adicionais:

| Tabela | Finalidade |
|---|---|
| loyalty_accounts | Saldo fictício de pontos por usuário |
| loyalty_entries | Histórico de créditos e débitos simulados |

Regras:

- Saldo nunca negativo.
- Conversão de pontos definida por configuração.
- Débito associado ao pedido.
- Proteção contra débito duplicado.
- Débito e confirmação do pedido na mesma transação.

Os valores iniciais e a taxa de conversão serão definidos na etapa de regras comerciais.

## 11. Ingressos

No MVP, cada registro confirmado em `order_items` representará um ingresso.

Cada ingresso terá um `ticket_code` único.

O pedido terá um `booking_code` único para agrupar seus ingressos.

O voucher exibirá:

- Filme.
- Cinema.
- Sala.
- Data e horário.
- Projeção e versão de áudio.
- Assento.
- Tipo de ingresso.
- Código do pedido.
- Código do ingresso.
- Aviso “SIMULAÇÃO — SEM VALIDADE”.

O QR Code não representará autorização de entrada em um cinema real.

## 12. Programação

Não serão permitidas sessões com intervalos sobrepostos na mesma sala.

O campo `room_available_at` incluirá o término da sessão e o intervalo operacional necessário antes da próxima sessão.

A projeção da sessão deverá existir entre os formatos suportados pela sala.

Sessões já iniciadas ou canceladas não poderão receber novas reservas.

## 13. Estado da conversa

O estado estruturado será persistido separadamente dos pedidos.

A aplicação poderá retomar o fluxo após uma interrupção, mas deverá revalidar:

- Existência da sessão.
- Horário da sessão.
- Validade da reserva.
- Disponibilidade dos assentos.
- Estado do pedido.
- Preços apresentados.
- Identidade do usuário.

Uma frase como “já paguei” não altera diretamente o estado do pagamento.

## 14. Testes obrigatórios do modelo

- Impedir assentos duplicados na mesma sala.
- Impedir dupla confirmação do mesmo assento na mesma sessão.
- Garantir reserva de grupo completa ou nenhuma reserva.
- Impedir confirmação após expiração.
- Impedir acesso ao pedido de outro usuário.
- Impedir preços e saldos negativos.
- Impedir pagamento duplicado.
- Impedir sessões sobrepostas na mesma sala.
- Preservar pedidos após reinicialização da aplicação.
- Manter pedidos confirmados consistentes após atualização do catálogo.

## 15. Status

Este documento define o modelo planejado.

A criação do esquema SQL, as migrações, os dados iniciais e os serviços de acesso serão realizados nas próximas etapas.
