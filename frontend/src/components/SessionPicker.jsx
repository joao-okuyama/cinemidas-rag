const money = (cents) =>
  new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(cents / 100);

const audioLabel = {
  DUBBED: "Dublado",
  SUBTITLED: "Legendado",
};

function sessionDate(value, timeZone) {
  const date = new Date(value);
  return new Intl.DateTimeFormat("pt-BR", {
    timeZone: timeZone || "America/Sao_Paulo",
    weekday: "short",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export default function SessionPicker({ sessions, selectedId, onSelect, disabled }) {
  return (
    <div className="session-grid">
      {sessions.map((session) => (
        <button
          key={session.session_id}
          type="button"
          disabled={disabled}
          className={`session-card ${
            selectedId === session.session_id ? "session-card--selected" : ""
          }`}
          onClick={() => onSelect(session)}
          aria-pressed={selectedId === session.session_id}
        >
          <strong>{session.cinema_name}</strong>
          <span>{sessionDate(session.starts_at_local, session.timezone)}</span>
          <span>
            {session.projection_format} · {audioLabel[session.audio_version] || session.audio_version}
          </span>
          <span className="session-card__price">
            A partir de {money(session.total_full_price_cents)}
          </span>
        </button>
      ))}
    </div>
  );
}
