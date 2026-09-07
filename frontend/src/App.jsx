import { useEffect, useMemo, useState } from "react";

import { bookingApi } from "./api";
import AgentPanel from "./components/AgentPanel";
import CheckoutPanel from "./components/CheckoutPanel";
import MovieCard from "./components/MovieCard";
import SeatSelection from "./components/SeatSelection";
import SessionPicker from "./components/SessionPicker";
import Ticket from "./components/Ticket";

const stages = ["Filme", "Sessão", "Assentos", "Pagamento"];

export default function App() {
  const [movies, setMovies] = useState([]);
  const [booking, setBooking] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [seats, setSeats] = useState([]);
  const [selectedSeats, setSelectedSeats] = useState([]);
  const [halfPriceSeats, setHalfPriceSeats] = useState([]);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [agentOpen, setAgentOpen] = useState(false);
  const [chatTurns, setChatTurns] = useState([]);
  const [isEditingSeats, setIsEditingSeats] = useState(false);

  function applyBooking(snapshot) {
    if (!snapshot) return;
    setBooking(snapshot);
    if (snapshot.sessions?.length) {
      setSessions(snapshot.sessions);
    }
    if (snapshot.seats?.length) {
      setSeats(snapshot.seats);
    }
    if (snapshot.order?.items?.length) {
      setSelectedSeats(snapshot.order.items.map((item) => item.seat_label));
      setHalfPriceSeats(
        snapshot.order.items
          .filter((item) => item.ticket_type === "HALF")
          .map((item) => item.seat_label)
      );
    }
  }

  useEffect(() => {
    let active = true;
    async function bootstrap() {
      setBusy(true);
      setError("");
      try {
        const [sessionData, catalogData] = await Promise.all([
          bookingApi.bootstrap(),
          bookingApi.catalog(),
        ]);
        if (!active) return;
        setMovies(catalogData.items || []);
        if (sessionData.booking) {
          applyBooking(sessionData.booking);
        }
        try {
          const historyData = await bookingApi.history();
          if (active && historyData.items) {
            setChatTurns(historyData.items);
          }
        } catch {
          // Guest history is optional on fresh visitor session
        }
      } catch (problem) {
        if (active) setError(problem.message);
      } finally {
        if (active) setBusy(false);
      }
    }
    bootstrap();
    return () => {
      active = false;
    };
  }, []);

  const currentMovie = booking?.movie || null;
  const currentSession = booking?.session || null;
  const currentOrder = booking?.order || null;
  const isConfirmed = currentOrder?.status === "CONFIRMED";
  const isAwaitingPayment = currentOrder?.status === "AWAITING_PAYMENT";

  const stage = isConfirmed || (isAwaitingPayment && !isEditingSeats)
    ? 3
    : currentSession
    ? 2
    : currentMovie
    ? 1
    : 0;

  const visibleMovies = useMemo(() => {
    const term = search.trim().toLocaleLowerCase("pt-BR");
    if (!term) return movies;
    return movies.filter((item) =>
      item.title.toLocaleLowerCase("pt-BR").includes(term)
    );
  }, [movies, search]);

  async function chooseMovie(selected) {
    setBusy(true);
    setError("");
    try {
      const data = await bookingApi.select({ movie_id: selected.movie_id });
      applyBooking(data.booking);
      setSelectedSeats([]);
      setHalfPriceSeats([]);
      setIsEditingSeats(false);
      setTimeout(() => {
        document.getElementById("sessions")?.scrollIntoView({ behavior: "smooth" });
      }, 50);
    } catch (problem) {
      setError(problem.message);
    } finally {
      setBusy(false);
    }
  }

  async function chooseSession(selected) {
    setBusy(true);
    setError("");
    try {
      const data = await bookingApi.select({
        movie_id: currentMovie?.movie_id || selected.movie_id,
        session_id: selected.session_id,
      });
      applyBooking(data.booking);
      setSelectedSeats([]);
      setHalfPriceSeats([]);
      setIsEditingSeats(false);
      setTimeout(() => {
        document.getElementById("seats")?.scrollIntoView({ behavior: "smooth" });
      }, 50);
    } catch (problem) {
      setError(problem.message);
    } finally {
      setBusy(false);
    }
  }

  function toggleSeat(label) {
    setSelectedSeats((current) => {
      if (current.includes(label)) {
        setHalfPriceSeats((halves) => halves.filter((seat) => seat !== label));
        return current.filter((seat) => seat !== label);
      }
      if (current.length >= 12) {
        setError("Limite máximo de 12 assentos por pedido atingido.");
        return current;
      }
      return [...current, label];
    });
  }

  function toggleTicketType(label) {
    setHalfPriceSeats((current) =>
      current.includes(label)
        ? current.filter((seat) => seat !== label)
        : [...current, label]
    );
  }

  async function continueToCheckout() {
    if (selectedSeats.length === 0) {
      setError("Selecione pelo menos um assento.");
      return;
    }
    setBusy(true);
    setError("");
    const requestId = `FLOW-${crypto.randomUUID()}`;
    try {
      const data = await bookingApi.checkout({
        movie_id: currentMovie.movie_id,
        session_id: currentSession.session_id,
        seat_labels: selectedSeats,
        half_price_seats: halfPriceSeats,
        request_id: requestId,
      });
      applyBooking(data.booking);
      setIsEditingSeats(false);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (problem) {
      setError(problem.message);
      try {
        const refreshed = await bookingApi.seats(currentSession.session_id);
        if (refreshed?.items) setSeats(refreshed.items);
      } catch {}
    } finally {
      setBusy(false);
    }
  }

  async function pay(method) {
    if (!currentOrder) return;
    setBusy(true);
    setError("");
    const idempotencyKey = `PAY-${currentOrder.order_id}-${method}-${crypto.randomUUID()}`;
    try {
      const data = await bookingApi.pay(currentOrder.order_id, {
        method,
        idempotency_key: idempotencyKey,
      });
      applyBooking(data.booking);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (problem) {
      setError(problem.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleEditSeats() {
    setIsEditingSeats(true);
    if (currentSession) {
      try {
        const refreshed = await bookingApi.seats(currentSession.session_id);
        if (refreshed?.items) setSeats(refreshed.items);
      } catch {}
    }
    setTimeout(() => {
      document.getElementById("seats")?.scrollIntoView({ behavior: "smooth" });
    }, 50);
  }

  async function startAgain() {
    setBusy(true);
    setError("");
    try {
      const data = await bookingApi.reset();
      applyBooking(data.booking);
      setSelectedSeats([]);
      setHalfPriceSeats([]);
      setIsEditingSeats(false);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (problem) {
      setError(problem.message);
    } finally {
      setBusy(false);
    }
  }

  async function sendAgentMessage(text) {
    setBusy(true);
    setError("");
    const requestId = `CHAT-${crypto.randomUUID()}`;
    try {
      const data = await bookingApi.chat(text, requestId);
      setChatTurns((current) => [...current, { message: text, turn: data.turn }]);
      if (data.booking) {
        applyBooking(data.booking);
      }
      return true;
    } catch (problem) {
      setError(problem.message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <header className="site-header">
        <a className="brand" href="#top" aria-label="CineMidas, início">
          <span>CM</span><strong>CineMidas</strong>
        </a>
        <nav aria-label="Navegação principal">
          <a href="#catalog">Em cartaz</a>
          <button
            type="button"
            className="agent-entry"
            onClick={() => setAgentOpen(true)}
            title="Conversar com assistente de IA"
          >
            ✦ Comprar com IA
          </button>
        </nav>
      </header>

      <main id="top">
        <section className="hero-section">
          <div>
            <span className="eyebrow">Rede fictícia CineViva</span>
            <h1>Sua próxima história começa aqui.</h1>
            <p>Escolha o filme, encontre uma sessão e reserve seu lugar em poucos passos.</p>
          </div>
          <div className="journey" aria-label={`Etapa ${stage + 1} de 4`}>
            {stages.map((label, index) => (
              <span key={label} className={index <= stage ? "journey__active" : ""}>
                <i>{index + 1}</i>{label}
              </span>
            ))}
          </div>
        </section>

        {error && <div className="error-banner" role="alert">{error}</div>}

        {isConfirmed ? (
          <>
            <Ticket order={currentOrder} />
            <div style={{ textAlign: "center", margin: "24px 0 64px" }}>
              <button
                type="button"
                className="primary-button"
                style={{ maxWidth: "320px", display: "inline-block" }}
                onClick={startAgain}
              >
                Fazer nova reserva
              </button>
            </div>
          </>
        ) : isAwaitingPayment && !isEditingSeats ? (
          <CheckoutPanel
            checkout={{
              order: currentOrder,
              hold_expires_at: booking.hold_expires_at,
              server_now: booking.server_now,
            }}
            busy={busy}
            onPay={pay}
            onEdit={handleEditSeats}
          />
        ) : (
          <>
            <section className="content-section" id="catalog">
              <div className="section-heading">
                <div><span className="eyebrow">Em cartaz</span><h2>Escolha seu filme</h2></div>
                <input
                  type="search"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Buscar filme"
                  aria-label="Buscar filme"
                />
              </div>
              {busy && movies.length === 0 ? (
                <p className="loading">Carregando catálogo…</p>
              ) : (
                <div className="movie-grid">
                  {visibleMovies.map((item) => (
                    <MovieCard
                      key={item.movie_id}
                      movie={item}
                      selected={currentMovie?.movie_id === item.movie_id}
                      onSelect={chooseMovie}
                    />
                  ))}
                </div>
              )}
            </section>

            {currentMovie && (
              <section className="content-section selection-section" id="sessions">
                <div className="section-heading">
                  <div><span className="eyebrow">{currentMovie.title}</span><h2>Escolha a sessão</h2></div>
                </div>
                <SessionPicker
                  sessions={sessions.length ? sessions : (booking?.sessions || [])}
                  selectedId={currentSession?.session_id}
                  onSelect={chooseSession}
                  disabled={busy}
                />
              </section>
            )}

            {currentSession && (
              <SeatSelection
                session={currentSession}
                seats={seats}
                selected={selectedSeats}
                halves={halfPriceSeats}
                busy={busy}
                onToggle={toggleSeat}
                onHalf={toggleTicketType}
                onContinue={continueToCheckout}
              />
            )}
          </>
        )}
      </main>

      {agentOpen && (
        <AgentPanel
          turns={chatTurns}
          busy={busy}
          onSend={sendAgentMessage}
          onClose={() => setAgentOpen(false)}
          onMovie={chooseMovie}
          onSession={chooseSession}
        />
      )}

      <footer>
        <strong>CineMidas</strong>
        <span>Protótipo educacional. Cinemas, sessões e pagamentos são simulados.</span>
        <span>Dados e imagens: TMDB. Não endossado ou certificado pelo TMDB.</span>
      </footer>
    </>
  );
}
