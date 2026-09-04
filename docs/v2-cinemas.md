# CineMidas v2 — Unidades e salas simuladas

## 1. Finalidade

Este documento define as unidades e salas fictícias utilizadas no simulador de compra de ingressos.

As unidades não representam estabelecimentos reais. Seus nomes, salas e capacidades são dados educacionais.

A referência a IMAX representa apenas uma categoria simulada de experiência, sem vínculo comercial ou certificação.

## 2. Área inicial de atendimento

O MVP atenderá à cidade de São Paulo, no estado de São Paulo.

Serão utilizadas três regiões:

- Centro.
- Zona Sul.
- Zona Oeste.

Se o usuário informar uma cidade não atendida, o agente deverá explicar a cobertura do simulador e perguntar se deseja consultar as unidades disponíveis.

O agente não deverá inventar unidades em outras cidades.

## 3. Unidades

| cinema_id | Nome | Cidade | UF | Região | Fuso horário |
|---|---|---|---|---|---|
| CV-CIN-001 | CineViva Centro | São Paulo | SP | Centro | America/Sao_Paulo |
| CV-CIN-002 | CineViva Sul | São Paulo | SP | Zona Sul | America/Sao_Paulo |
| CV-CIN-003 | CineViva Oeste | São Paulo | SP | Zona Oeste | America/Sao_Paulo |

Os identificadores são estáveis e não deverão ser alterados quando houver mudança no nome de exibição.

## 4. Salas

| room_id | cinema_id | Nome | Categoria | Projeções suportadas | Capacidade simulada |
|---|---|---|---|---|---|
| CV-ROOM-001 | CV-CIN-001 | Sala 1 | Standard | 2D e 3D | 120 |
| CV-ROOM-002 | CV-CIN-001 | Sala 2 | VIP | 2D | 120 |
| CV-ROOM-003 | CV-CIN-002 | Sala 1 | Standard | 2D e 3D | 120 |
| CV-ROOM-004 | CV-CIN-002 | Sala 2 | IMAX simulado | 2D e 3D | 120 |
| CV-ROOM-005 | CV-CIN-003 | Sala 1 | Standard | 2D | 120 |
| CV-ROOM-006 | CV-CIN-003 | Sala 2 | VIP | 2D e 3D | 120 |

Para simplificar o MVP, todas as salas utilizam a mesma capacidade. Isso não representa uma especificação real de salas VIP ou IMAX.

## 5. Mapa de assentos

Cada sala terá:

- Dez fileiras, identificadas de A até J.
- Doze assentos por fileira, numerados de 1 até 12.
- Um total de 120 posições.
- Tela localizada à frente da fileira A.
- Fileira J localizada no fundo da sala.

Exemplos de assentos válidos:

- A1.
- C12.
- F6.
- F7.
- J12.

Os assentos 6 e 7 representam o centro horizontal de cada fileira.

O mapa inicial será retangular, sem corredores internos. Layouts específicos e posições acessíveis deverão ser modelados explicitamente em uma evolução posterior, sem pressupor que este mapa genérico os representa.

## 6. Identificação e disponibilidade

Um assento físico é identificado pela combinação:

- `room_id`
- `seat_label`

A disponibilidade pertence à sessão, não apenas à sala.

Por exemplo, F6 pode estar ocupado em uma sessão das 18h e disponível em outra sessão das 21h na mesma sala.

A identificação de disponibilidade deverá utilizar:

- `session_id`
- `seat_label`

## 7. Categoria, projeção e idioma

As seguintes características deverão permanecer separadas:

### Categoria da sala

- Standard.
- VIP.
- IMAX simulado.

### Projeção da sessão

- 2D.
- 3D.

### Versão de áudio e legendas da sessão

- Dublado.
- Legendado.
- Original em português, quando aplicável.

Uma sala pode suportar 2D e 3D, mas cada sessão deverá informar exatamente qual projeção utiliza.

O idioma e as legendas pertencem à sessão. O agente não deverá presumir que todas as sessões de um filme possuem a mesma versão.

## 8. Localização e distâncias

Neste estágio, os registros contêm apenas cidade e região.

Endereços e coordenadas ainda não foram definidos.

Enquanto não houver coordenadas de referência:

- Não calcular distâncias em quilômetros.
- Não informar tempo de deslocamento.
- Não afirmar que uma unidade é a mais próxima.
- Permitir filtragem pela cidade e região informadas.
- Explicar que a comparação de distância ainda não está disponível.

Quando forem adicionadas coordenadas simuladas, essa condição deverá ser informada ao usuário.

Distâncias em linha reta deverão ser identificadas como aproximadas e não poderão ser apresentadas como distância de trajeto.

## 9. Regras de programação

Cada sessão deverá referenciar:

- Um filme.
- Uma sala.
- Uma data e horário com fuso definido.
- Uma projeção suportada pela sala.
- Uma versão de áudio e legendas.
- Uma tabela de preços simulados.

A unidade será obtida pela sala vinculada à sessão.

Não será permitido criar duas sessões com horários sobrepostos na mesma sala, considerando a duração do filme e o intervalo operacional definido pela aplicação.

## 10. Limites desta etapa

Este documento não cria:

- Sessões.
- Preços.
- Disponibilidade de assentos.
- Reservas.
- Pagamentos.
- Pedidos.

Esses elementos serão implementados nas próximas etapas.
