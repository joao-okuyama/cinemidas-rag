import { useEffect, useMemo, useState } from "react";

import { bookingApi } from "./api";
import CheckoutPanel from "./components/CheckoutPanel";
import MovieCard from "./components/MovieCard";
import SeatMap from "./components/SeatMap";
import SessionPicker from "./components/SessionPicker";

const stages = ["Filme", "Sessão", "Assentos", "Pagamento"];

function storedId(key, prefix) {
  const existing = window.localStorage.getItem(key);
  if (existing) return existing;
  const value = `${prefix}-${crypto.randomUUID()}`;
  window.localStorage.setItem(key, value);
  return value;
}

export default function App() {
  const [movies, setMovies] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [seats, setSeats] = useState([]);
  const [movie, setMovie] = useState(null);
  const [session, setSession] = useState(null);
  const [selectedSeats, setSelectedSeats] = useState([]);
  const [halfPriceSeats, setHalfPriceSeats] = useState([]);
  const [checkout, setCheckout] = useState(null);
  const [confirmation, setConfirmation] = useState(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");

  const userId = useMemo(() => storedId("cinemidas-user-id", "WEB-USER"), []);
  const [conversationId, setConversationId] = useState(() =>
    `WEB-SITE-${crypto.randomUUID()}`,
  );

  const stage = confirmation || checkout ? 3 : session ? 2 : movie ? 1 : 0;

  useEffect(() => {
    bookingApi
      .catalog()
      .then((response) => setMovies(response.items))
      .catch((problem) => setError(problem.message))
      .finally(() => setBusy(false));
  }, []);

  const visibleMovies = movies.filter((item) =>
    item.title.toLocaleLowerCase("pt-BR").includes(search.toLocaleLowerCase("pt-BR")),
  );

  async function chooseMovie(selected) {
    setBusy(true);
    setError("");
    setMovie(selected);
    setSession(null);
    setSeats([]);
    setSelectedSeats([]);
    setHalfPriceSeats([]);
    setCheckout(null);
    try {
      const response = await bookingApi.sessions(selected.movie_id);
      setSessions(response.items);
      document.getElementById("sessions")?.scrollIntoView({ behavior: "smooth" });
    } catch (problem) {
      setError(problem.message);
    } finally {
      setBusy(false);
    }
  }

  async function chooseSession(selected) {
    setBusy(true);
    setError("");
    setSession(selected);
    setSelectedSeats([]);
    setHalfPriceSeats([]);
    setCheckout(null);
    try {
      const response = await bookingApi.seats(selected.session_id, userId);
      setSeats(response.items);
      document.getElementById("seats")?.scrollIntoView({ behavior: "smooth" });
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
      return [...current, label];
    });
  }

  function toggleTicketType(label) {
    setHalfPriceSeats((current) =>
      current.includes(label)
        ? current.filter((seat) => seat !== label)
        : [...current, label],
    );
  }

  async function continueToCheckout() {
    setBusy(true);
    setError("");
    try {
      const response = await bookingApi.checkout({
        user_id: userId,
        conversation_id: conversationId,
        movie_id: movie.movie_id,
        session_id: session.session_id,
        seat_labels: selectedSeats,
        half_price_seats: halfPriceSeats,
      });
      setCheckout(response);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (problem) {
      setError(problem.message);
      const refreshed = await bookingApi.seats(session.session_id, userId).catch(() => null);
      if (refreshed) setSeats(refreshed.items);
    } finally {
      setBusy(false);
    }
  }

  async function pay(method) {
    setBusy(true);
    setError("");
    try {
      const response = await bookingApi.pay(checkout.order.order_id, {
        user_id: userId,
        method,
        idempotency_key: `${checkout.order.order_id}-${method}`,
      });
      setConfirmation(response);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (problem) {
      setError(problem.message);
    } finally {
      setBusy(false);
    }
  }

  function startAgain() {
    setMovie(null);
    setSession(null);
    setSessions([]);
    setSeats([]);
    setSelectedSeats([]);
    setHalfPriceSeats([]);
    setCheckout(null);
    setConfirmation(null);
    setConversationId(`WEB-SITE-${crypto.randomUUID()}`);
    setError("");
  }

  return (
    <>
      <header className="site-header">
        <a className="brand" href="#top" aria-label="CineMidas, início">
          <span>CM</span><strong>CineMidas</strong>
        </a>
        <nav aria-label="Navegação principal">
          <a href="#catalog">Em cartaz</a>
          <button type="button" className="agent-entry" disabled title="Próxima etapa">
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

        {confirmation ? (
          <section className="confirmation-card">
            <span className="confirmation-card__icon">✓</span>
            <span className="eyebrow">Pagamento simulado aprovado</span>
            <h1>Seu lugar está garantido.</h1>
            <p className="booking-code">{confirmation.order.booking_code}</p>
            <div className="ticket-details">
              <strong>{confirmation.order.movie_title}</strong>
              <span>{confirmation.order.cinema_name} · {confirmation.order.room_name}</span>
              <span>Assentos {confirmation.order.items.map((item) => item.seat_label).join(", ")}</span>
            </div>
            <div className="mock-qr" aria-label="QR Code meramente ilustrativo">QR</div>
            <p className="simulation-notice">SIMULAÇÃO — SEM VALIDADE</p>
            <button type="button" className="primary-button" onClick={startAgain}>
              Fazer nova reserva
            </button>
          </section>
        ) : checkout ? (
          <CheckoutPanel checkout={checkout} busy={busy} onPay={pay} />
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
                      selected={movie?.movie_id === item.movie_id}
                      onSelect={chooseMovie}
                    />
                  ))}
                </div>
              )}
            </section>

            {movie && (
              <section className="content-section selection-section" id="sessions">
                <div className="section-heading">
                  <div><span className="eyebrow">{movie.title}</span><h2>Escolha a sessão</h2></div>
                </div>
                <SessionPicker sessions={sessions} selectedId={session?.session_id} onSelect={chooseSession} />
              </section>
            )}

            {session && (
              <section className="content-section selection-section" id="seats">
                <div className="section-heading">
                  <div><span className="eyebrow">{session.cinema_name}</span><h2>Escolha seus lugares</h2></div>
                  <strong>{selectedSeats.length} selecionado(s)</strong>
                </div>
                <SeatMap seats={seats} selectedSeats={selectedSeats} onToggle={toggleSeat} />

                {selectedSeats.length > 0 && (
                  <div className="ticket-types">
                    <div><span className="eyebrow">Ingressos</span><h2>Inteira ou meia?</h2></div>
                    {selectedSeats.map((label) => (
                      <div className="ticket-row" key={label}>
                        <strong>Assento {label}</strong>
                        <div className="segmented-control">
                          <button
                            type="button"
                            className={!halfPriceSeats.includes(label) ? "active" : ""}
                            onClick={() => halfPriceSeats.includes(label) && toggleTicketType(label)}
                          >Inteira</button>
                          <button
                            type="button"
                            className={halfPriceSeats.includes(label) ? "active" : ""}
                            onClick={() => !halfPriceSeats.includes(label) && toggleTicketType(label)}
                          >Meia</button>
                        </div>
                      </div>
                    ))}
                    <button
                      type="button"
                      className="primary-button"
                      disabled={busy}
                      onClick={continueToCheckout}
                    >{busy ? "Preparando pedido…" : "Continuar"}</button>
                    <p className="helper-text">Os lugares serão protegidos por 5 minutos ao continuar.</p>
                  </div>
                )}
              </section>
            )}
          </>
        )}
      </main>

      <footer>
        <strong>CineMidas</strong>
        <span>Protótipo educacional. Cinemas, sessões e pagamentos são simulados.</span>
        <span>Dados e imagens: TMDB. Não endossado ou certificado pelo TMDB.</span>
      </footer>
    </>
  );
}
