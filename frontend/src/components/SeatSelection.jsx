import SeatMap from "./SeatMap";
export default function SeatSelection({ session, seats, selected, halves, busy, onToggle, onHalf, onContinue }) {
  return <section className="content-section selection-section" id="seats">
    <div className="section-heading"><div><span className="eyebrow">{session.cinema_name}</span>
      <h2>Escolha seus lugares</h2></div><strong>{selected.length}/12 selecionados</strong></div>
    <SeatMap seats={seats} selectedSeats={selected} onToggle={onToggle} disabled={busy} />
    {selected.length > 0 && <div className="ticket-types">
      <h3>Inteira ou meia?</h3>
      {selected.map((label) => <div className="ticket-row" key={label}>
        <strong>Assento {label}</strong><label>
          <input type="checkbox" checked={halves.includes(label)} disabled={busy}
            onChange={() => onHalf(label)} /> Meia-entrada
        </label>
      </div>)}
      <button type="button" className="primary-button" disabled={busy} onClick={onContinue}>
        {busy ? "Preparando pedido…" : "Continuar"}
      </button>
      <p className="helper-text">Ao continuar, reservamos os lugares por 5 minutos e calculamos o total automaticamente.</p>
    </div>}
  </section>;
}
