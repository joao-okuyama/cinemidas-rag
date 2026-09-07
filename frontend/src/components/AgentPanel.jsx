import { useEffect, useRef, useState } from "react";
import MovieCarousel from "./MovieCarousel";
import SessionPicker from "./SessionPicker";
import SeatMap from "./SeatMap";
import Ticket from "./Ticket";
import { money } from "../format";

function TypewriterAnswer({ text, isLatest }) {
  const [displayedLength, setDisplayedLength] = useState(isLatest ? 0 : text.length);
  const [isTyping, setIsTyping] = useState(isLatest && text.length > 0);

  useEffect(() => {
    if (!isLatest) {
      setDisplayedLength(text.length);
      setIsTyping(false);
      return;
    }

    setDisplayedLength(0);
    setIsTyping(true);

    let current = 0;
    const chunk = Math.max(1, Math.ceil(text.length / 32));
    const timer = setInterval(() => {
      current += chunk;
      if (current >= text.length) {
        setDisplayedLength(text.length);
        setIsTyping(false);
        clearInterval(timer);
      } else {
        setDisplayedLength(current);
      }
    }, 18);

    return () => clearInterval(timer);
  }, [text, isLatest]);

  return (
    <p className="chat-answer">
      {text.slice(0, displayedLength)}
      {isTyping && <span className="typing-cursor" aria-hidden="true">▌</span>}
    </p>
  );
}

export default function AgentPanel({
  turns,
  busy,
  pendingMessage,
  onSend,
  onClose,
  onMovie,
  onSession,
  children,
}) {
  const [message, setMessage] = useState("");
  const [selectedSeats, setSelectedSeats] = useState([]);
  const [halfPriceSeats, setHalfPriceSeats] = useState([]);
  const input = useRef();
  const dialog = useRef();
  const end = useRef();

  useEffect(() => {
    const previous = document.activeElement;
    if (dialog.current && !dialog.current.open) {
      dialog.current.showModal();
    }
    input.current?.focus();
    return () => previous?.focus();
  }, []);

  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [turns.length, busy, pendingMessage]);

  // Reset local interactive selections when turn changes
  useEffect(() => {
    setSelectedSeats([]);
    setHalfPriceSeats([]);
  }, [turns.length]);

  async function submit(event) {
    event.preventDefault();
    if (!message.trim() || busy) return;
    const textToSend = message.trim();
    setMessage("");
    await onSend(textToSend);
  }

  function handleMovieClick(movie) {
    if (busy) return;
    onSend(`Quero assistir ${movie.title} (${movie.movie_id})`);
  }

  function handleSessionClick(session) {
    if (busy) return;
    onSend(`Quero a sessão ${session.session_id}`);
  }

  function toggleSeat(label) {
    setSelectedSeats((current) =>
      current.includes(label)
        ? current.filter((seat) => seat !== label)
        : current.length >= 12
        ? current
        : [...current, label]
    );
  }

  return (
    <dialog
      ref={dialog}
      className="agent-dialog"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <header>
        <div>
          <span className="eyebrow">Mesma compra, outra maneira</span>
          <h2>Comprar com IA</h2>
        </div>
        <button
          type="button"
          className="secondary-button"
          onClick={onClose}
          aria-label="Fechar chat"
        >
          Fechar ×
        </button>
      </header>

      <div className="agent-scroll">
        <p>
          Encontre filmes, escolha uma sessão e conclua uma reserva simulada. Você pode alternar entre conversa e botões.
        </p>

        <div role="log" aria-live="polite" aria-relevant="additions">
          {turns.map((entry, index) => {
            const isLatest = index === turns.length - 1;
            const turn = entry.turn;
            const view = turn?.view;
            const payload = turn?.payload;

            return (
              <article className="chat-turn" key={entry.id || index}>
                <p className="chat-user">{entry.message}</p>
                <TypewriterAnswer text={turn.text} isLatest={isLatest && !busy} />

                {view === "catalog" && Array.isArray(payload) && (
                  <MovieCarousel movies={payload} onSelect={handleMovieClick} disabled={busy} />
                )}

                {view === "sessions" && Array.isArray(payload) && (
                  <SessionPicker
                    sessions={payload}
                    onSelect={handleSessionClick}
                    disabled={busy}
                  />
                )}

                {view === "seat_map" && payload?.seats && (
                  <div className="chat-seat-selection">
                    <SeatMap
                      seats={payload.seats}
                      selectedSeats={isLatest ? selectedSeats : []}
                      onToggle={isLatest ? toggleSeat : undefined}
                      disabled={busy || !isLatest}
                    />
                    {isLatest && (
                      <div className="chat-action-bar">
                        <span>
                          {selectedSeats.length === 0
                            ? "Clique nos assentos desejados no mapa acima"
                            : `Assentos: ${selectedSeats.join(", ")}`}
                        </span>
                        <button
                          type="button"
                          className="primary-button"
                          disabled={busy || selectedSeats.length === 0}
                          onClick={() => {
                            if (selectedSeats.length > 0) {
                              onSend(`Quero os assentos ${selectedSeats.join(" e ")}`);
                            }
                          }}
                        >
                          Confirmar assentos {selectedSeats.length > 0 ? `(${selectedSeats.length})` : ""}
                        </button>
                      </div>
                    )}
                  </div>
                )}

                {view === "hold" && payload?.seat_labels && (
                  <div className="chat-hold-selection">
                    <div className="chat-ticket-types">
                      {payload.seat_labels.map((label) => {
                        const isHalf = halfPriceSeats.includes(label);
                        return (
                          <div key={label} className="chat-ticket-toggle">
                            <span>Assento <strong>{label}</strong></span>
                            <div className="chat-type-buttons">
                              <button
                                type="button"
                                className={!isHalf ? "active-type" : ""}
                                disabled={busy || !isLatest}
                                onClick={() =>
                                  setHalfPriceSeats((curr) => curr.filter((s) => s !== label))
                                }
                              >
                                Inteira
                              </button>
                              <button
                                type="button"
                                className={isHalf ? "active-type" : ""}
                                disabled={busy || !isLatest}
                                onClick={() =>
                                  setHalfPriceSeats((curr) =>
                                    curr.includes(label) ? curr : [...curr, label]
                                  )
                                }
                              >
                                Meia
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                    {isLatest && (
                      <div className="chat-action-bar">
                        <span>
                          {payload.seat_labels.length} ingresso(s) reservado(s)
                        </span>
                        <button
                          type="button"
                          className="primary-button"
                          disabled={busy}
                          onClick={() => {
                            const desc = payload.seat_labels
                              .map(
                                (s) =>
                                  `${s} ${halfPriceSeats.includes(s) ? "meia" : "inteira"}`
                              )
                              .join(", ");
                            onSend(`Confirmar ingressos: ${desc}`);
                          }}
                        >
                          Avançar para pagamento
                        </button>
                      </div>
                    )}
                  </div>
                )}

                {view === "checkout" && payload && (
                  <div className="chat-checkout">
                    <div className="chat-order-summary">
                      <div className="chat-price-lines">
                        <span>Ingressos: <strong>{money(payload.subtotal_cents)}</strong></span>
                        {payload.discount_cents > 0 && (
                          <span>Descontos: <strong>− {money(payload.discount_cents)}</strong></span>
                        )}
                        <span>Taxas: <strong>{money(payload.fee_cents)}</strong></span>
                        <span className="chat-total-line">
                          Total: <strong>{money(payload.total_cents)}</strong>
                        </span>
                      </div>
                    </div>
                    {isLatest && (
                      <div className="chat-payment-buttons">
                        <button
                          type="button"
                          className="payment-button"
                          disabled={busy}
                          onClick={() => onSend("Confirmo o pagamento com PIX")}
                        >
                          <strong>Pagar com PIX</strong>
                          <span>Simulação instantânea</span>
                        </button>
                        <button
                          type="button"
                          className="payment-button"
                          disabled={busy}
                          onClick={() => onSend("Confirmo o pagamento com Cartão")}
                        >
                          <strong>Pagar com Cartão</strong>
                          <span>Simulação de crédito</span>
                        </button>
                        <button
                          type="button"
                          className="payment-button"
                          disabled={busy}
                          onClick={() => onSend("Confirmo o pagamento com Pontos")}
                        >
                          <strong>Pontos CineViva</strong>
                          <span>Resgate simulado</span>
                        </button>
                      </div>
                    )}
                  </div>
                )}

                {view === "voucher" && (
                  <div className="chat-voucher">
                    {payload?.order ? (
                      <Ticket order={payload.order} />
                    ) : (
                      <pre className="chat-ascii-ticket">
                        {payload?.voucher || turn.text}
                      </pre>
                    )}
                  </div>
                )}
              </article>
            );
          })}

          {pendingMessage && (
            <article className="chat-turn chat-turn--pending">
              <p className="chat-user">{pendingMessage}</p>
              <div className="chat-typing-indicator" aria-label="CineMidas está digitando">
                <div className="typing-header">
                  <span className="typing-sparkle">✦</span>
                  <span className="typing-author">CineMidas</span>
                  <span className="typing-hint">digitando…</span>
                </div>
                <div className="typing-bubble">
                  <span className="typing-dot"></span>
                  <span className="typing-dot"></span>
                  <span className="typing-dot"></span>
                </div>
              </div>
            </article>
          )}
        </div>
        <div ref={end} />
        {children}
      </div>

      <form className="chat-form" onSubmit={submit}>
        <label className="sr-only" htmlFor="agent-message">
          Mensagem para o CineMidas
        </label>
        <input
          ref={input}
          id="agent-message"
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          maxLength={2000}
          placeholder="Digite sua mensagem ou use os botões acima…"
          disabled={busy}
        />
        <button
          type="submit"
          className="primary-button"
          disabled={busy || !message.trim()}
        >
          {busy ? "Aguarde…" : "Enviar"}
        </button>
      </form>
    </dialog>
  );
}
