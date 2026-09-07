import { audioLabel, money, sessionDate } from "../format";
export default function Ticket({ order }) {
  return <section className="confirmation-card">
    <span className="eyebrow">{order.status === "CONFIRMED" ? "Pagamento simulado aprovado" : order.status}</span>
    <h2>{order.movie_title}</h2>
    {order.booking_code && <p className="booking-code">{order.booking_code}</p>}
    <div className="ticket-details">
      <strong>{order.cinema_name} · {order.room_name}</strong>
      <span>{sessionDate(order.session_starts_at, order.cinema_timezone)} ({order.cinema_timezone})</span>
      <span>{order.projection_format} · {audioLabel(order.audio_version)}</span>
      {order.items.map((item) => <span key={item.seat_label}>
        {item.seat_label} · {item.ticket_type === "HALF" ? "Meia" : "Inteira"} · {money(item.total_cents)}
        {item.ticket_code && <small> · {item.ticket_code}</small>}
      </span>)}
      <strong>Total: {money(order.total_cents)}</strong>
    </div>
    {order.booking_code && <div className="mock-qr" aria-label="QR ilustrativo, não escaneável">QR</div>}
    <p className="simulation-notice">SIMULAÇÃO — SEM VALIDADE</p>
  </section>;
}
