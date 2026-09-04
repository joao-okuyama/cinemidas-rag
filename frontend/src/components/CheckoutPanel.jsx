import { useEffect, useState } from "react";

const money = (cents) =>
  new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(cents / 100);

export default function CheckoutPanel({ checkout, busy, onPay }) {
  const [seconds, setSeconds] = useState(0);
  const order = checkout.order;

  useEffect(() => {
    const update = () => {
      setSeconds(
        Math.max(0, checkout.hold_expires_at - Math.floor(Date.now() / 1000)),
      );
    };
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, [checkout.hold_expires_at]);

  const countdown = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(
    seconds % 60,
  ).padStart(2, "0")}`;

  return (
    <div className="checkout-layout">
      <section className="summary-card">
        <div className="summary-card__heading">
          <div>
            <span className="eyebrow">Resumo do pedido</span>
            <h2>{order.movie_title}</h2>
          </div>
          <span className={`countdown ${seconds === 0 ? "countdown--expired" : ""}`}>
            {seconds > 0 ? `Reserva ${countdown}` : "Reserva expirada"}
          </span>
        </div>

        <p>{order.cinema_name} · {order.room_name}</p>
        <p>Assentos {order.items.map((item) => item.seat_label).join(", ")}</p>

        <div className="price-lines">
          <span>Ingressos <strong>{money(order.subtotal_cents)}</strong></span>
          <span>Descontos <strong>− {money(order.discount_cents)}</strong></span>
          <span>Taxas <strong>{money(order.fee_cents)}</strong></span>
          <span className="price-lines__total">
            Total <strong>{money(order.total_cents)}</strong>
          </span>
        </div>
      </section>

      <section className="payment-card">
        <span className="eyebrow">Pagamento simulado</span>
        <h2>Como deseja pagar?</h2>
        <p>Nenhum dado financeiro real será solicitado.</p>
        <button disabled={busy || seconds === 0} onClick={() => onPay("PIX_MOCK")}>
          <strong>PIX</strong><span>Aprovação imediata simulada</span>
        </button>
        <button disabled={busy || seconds === 0} onClick={() => onPay("CARD_MOCK")}>
          <strong>Cartão</strong><span>Tokenização simulada</span>
        </button>
        <button disabled={busy || seconds === 0} onClick={() => onPay("LOYALTY_MOCK")}>
          <strong>Pontos CineViva</strong><span>Resgate simulado</span>
        </button>
      </section>
    </div>
  );
}
