import { useEffect, useRef, useState } from "react";
import MovieCard from "./MovieCard";
import SessionPicker from "./SessionPicker";

export default function AgentPanel({ turns, busy, onSend, onClose, onMovie, onSession, children }) {
  const [message, setMessage] = useState("");
  const input = useRef();
  const dialog = useRef();
  const end = useRef();
  useEffect(() => {
    const previous = document.activeElement;
    dialog.current.showModal();
    input.current.focus();
    return () => previous?.focus();
  }, []);
  useEffect(() => { end.current?.scrollIntoView({ block: "nearest" }); }, [turns.length]);
  async function submit(event) {
    event.preventDefault();
    if (!message.trim() || busy) return;
    if (await onSend(message.trim())) setMessage("");
  }
  return <dialog ref={dialog} className="agent-dialog" onCancel={(event) => { event.preventDefault(); onClose(); }}>
    <header><div><span className="eyebrow">Mesma compra, outra maneira</span><h2>Comprar com IA</h2></div>
      <button type="button" className="secondary-button" onClick={onClose} aria-label="Fechar chat">Fechar ×</button></header>
    <div className="agent-scroll">
      <p>Encontre filmes, escolha uma sessão e conclua uma reserva simulada. Você pode alternar entre conversa e botões.</p>
      <div role="log" aria-live="polite" aria-relevant="additions">
        {turns.map((entry, index) => <article className="chat-turn" key={entry.id || index}>
          <p className="chat-user">{entry.message}</p>
          <p className="chat-answer">{entry.turn.text}</p>
          {entry.turn.view === "catalog" && <div className="movie-grid chat-catalog">
            {entry.turn.payload.map((movie) => <MovieCard key={movie.movie_id} movie={movie}
              onSelect={onMovie} disabled={busy} />)}
          </div>}
          {entry.turn.view === "sessions" && <SessionPicker sessions={entry.turn.payload}
            onSelect={onSession} disabled={busy} />}
        </article>)}
      </div>
      <div ref={end} />
      {children}
    </div>
    <form className="chat-form" onSubmit={submit}>
      <label className="sr-only" htmlFor="agent-message">Mensagem para o CineMidas</label>
      <input ref={input} id="agent-message" value={message} onChange={(event) => setMessage(event.target.value)}
        maxLength={2000} placeholder="Quero dois lugares no meio da fileira F…" disabled={busy} />
      <button type="submit" className="primary-button" disabled={busy || !message.trim()}>{busy ? "Aguarde…" : "Enviar"}</button>
    </form>
  </dialog>;
}
