import { ratingLabel } from "../format";
export default function MovieCard({ movie, selected, onSelect, disabled }) {
  const details = [
    movie.runtime_minutes ? `${movie.runtime_minutes} min` : null,
    ratingLabel(movie.age_rating),
  ].filter(Boolean);

  return (
    <button
      className={`movie-card ${selected ? "movie-card--selected" : ""}`}
      type="button"
      disabled={disabled}
      onClick={() => onSelect(movie)}
      aria-pressed={selected}
    >
      <div className="movie-card__poster">
        {movie.poster_url ? (
          <img src={movie.poster_url} loading="lazy" alt={`Pôster de ${movie.title}`} />
        ) : (
          <span aria-hidden="true">🎬</span>
        )}
        <span className="movie-card__availability">Sessões disponíveis</span>
      </div>
      <div className="movie-card__body">
        <h3>{movie.title}</h3>
        <p>{details.join(" · ")}</p>
        <p className="movie-card__genres">
          {movie.genres?.slice(0, 3).join(" · ") || "Gênero não informado"}
        </p>
      </div>
    </button>
  );
}
