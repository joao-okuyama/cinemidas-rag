export default function SeatMap({ seats, selectedSeats, onToggle }) {
  const rows = seats.reduce((grouped, seat) => {
    grouped[seat.row] = [...(grouped[seat.row] || []), seat];
    return grouped;
  }, {});

  return (
    <div className="seat-area">
      <div className="screen" aria-label="Posição da tela">
        TELA
      </div>

      <div className="seat-map">
        {Object.entries(rows).map(([row, rowSeats]) => (
          <div className="seat-row" key={row}>
            <span className="seat-row__label">{row}</span>
            <div className="seat-row__seats">
              {rowSeats.map((seat) => {
                const selected = selectedSeats.includes(seat.label);
                const unavailable = seat.status !== "AVAILABLE";

                return (
                  <button
                    key={seat.label}
                    type="button"
                    className={`seat ${selected ? "seat--selected" : ""} ${
                      unavailable ? "seat--occupied" : ""
                    }`}
                    disabled={unavailable}
                    onClick={() => onToggle(seat.label)}
                    aria-pressed={selected}
                    aria-label={`Assento ${seat.label}${
                      unavailable ? ", indisponível" : selected ? ", selecionado" : ", disponível"
                    }`}
                  >
                    {seat.number}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      <div className="seat-legend">
        <span><i className="legend-swatch legend-swatch--available" />Disponível</span>
        <span><i className="legend-swatch legend-swatch--selected" />Selecionado</span>
        <span><i className="legend-swatch legend-swatch--occupied" />Ocupado</span>
      </div>
    </div>
  );
}
