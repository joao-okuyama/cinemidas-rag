import { useEffect, useState } from "react";
import { audioLabel, money, sessionDate } from "../format";

export default function CheckoutPanel({ checkout, busy, onPay, onEdit }) {
  const order = checkout.order;
  const [remaining, setRemaining] = useState(() =>
    Math.max(0, checkout.hold_expires_at - checkout.server_now));
  useEffect(() => {
    const deadline = performance.now() + Math.max(0, checkout.hold_expires_at - checkout.server_now) * 1000;
    const update = () => setRemaining(Math.max(0, Math.ceil((deadline - performance.now()) / 1000)));
    update();
    const timer = setInterval(update, 500);
    return () => clearInterval(timer);
  }, [checkout.hold_expires_at, checkout.server_now]);
  const expired = remaining === 0 || order.status !== "AWAITING_PAYMENT";
  return <div className="checkout-layout">
    <section className="summary-card">
      <div className="summary-card__heading"><div>
        <span className="eyebrow">Resumo do pedido</span><h2>{order.movie_title}</h2>
      </div><span className={`countdown ${expired ? "countdown--expired" : ""}`}>
        {expired ? "Reserva expirada" : `Reserva ${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, "0")}`}
      </span></div>
      <p>{order.cinema_name} · {order.room_name}</p>
      <p>{sessionDate(order.session_starts_at, order.cinema_timezone)} · {order.projection_format} · {audioLabel(order.audio_version)}</p>
      {order.items.map((item) => <p key={item.seat_label}>{item.seat_label} · {item.ticket_type === "HALF" ? "Meia" : "Inteira"} · {money(item.total_cents)}</p>)}
      <div className="price-lines">
        <span>Ingressos <strong>{money(order.subtotal_cents)}</strong></span>
        <span>Descontos <strong>− {money(order.discount_cents)}</strong></span>
        <span>Taxas <strong>{money(order.fee_cents)}</strong></span>
        <span className="price-lines__total">Total <strong>{money(order.total_cents)}</strong></span>
      </div>
      <button type="button" className="secondary-button" disabled={busy} onClick={onEdit}>
        {expired ? "Consultar lugares novamente" : "Voltar e alterar assentos"}
      </button>
      {expired && <p role="status">O prazo terminou. Verifique a disponibilidade antes de continuar.</p>}
    </section>
    <section className="payment-card">
      <span className="eyebrow">Pagamento simulado</span><h2>Confirme para concluir</h2>
      <p>Nenhum dado financeiro real será solicitado. O botão confirma apenas a simulação.</p>
      {[["PIX_MOCK", "PIX"], ["CARD_MOCK", "Cartão"], ["LOYALTY_MOCK", "Pontos CineViva"]].map(([method, label]) =>
        <button key={method} type="button" disabled={busy || expired} onClick={() => onPay(method)}>
          <strong>Confirmar pagamento com {label}</strong><span>Simulação sem cobrança real</span>
        </button>)}
    </section>
  </div>;
}
